"""
Daily Telegram News Digest Bot
------------------------------
Fetches the latest news on a topic (via GNews API), summarizes each article
into a punchy one-liner using Gemini, and sends a formatted digest to a
Telegram chat/group.

Required environment variables (set as GitHub Actions secrets, or in a local .env):
    TELEGRAM_BOT_TOKEN   - from @BotFather
    TELEGRAM_CHAT_ID     - the target group's chat id (e.g. -1001234567890)
    GNEWS_API_KEY        - from https://gnews.io
    GEMINI_API_KEY       - from https://aistudio.google.com/apikey (free tier)
    NEWS_TOPIC           - the topic to search for, e.g. "artificial intelligence"
                           (defaults to "technology" if not set)
"""

import os
import sys
import json
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta

# ---------- Config ----------
GNEWS_MAX_ARTICLES = 5          # how many articles to pull from GNews
DIGEST_ARTICLE_COUNT = 5        # how many to include in the final digest (short format)
GNEWS_LOOKBACK_HOURS = 24        # GNews window - kept tight since this runs daily;
                                 # the Google News RSS fallback covers cases where
                                 # GNews has nothing fresh in the last 24h
GEMINI_MODEL = "gemini-2.5-flash"  # fast, free-tier-friendly model
SGT = timezone(timedelta(hours=8))  # Singapore Time

TOPIC = os.environ.get("NEWS_TOPIC", "technology")
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GNEWS_API_KEY = os.environ["GNEWS_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]


def fetch_news_gnews(topic: str) -> list[dict]:
    """Fetch latest articles on a topic from GNews, bounded to the last
    GNEWS_LOOKBACK_HOURS (default: 24 hours — this runs daily, so only
    genuinely new-since-yesterday articles are wanted here; if GNews has
    nothing in that window, fetch_news() falls back to Google News RSS).
    """
    url = "https://gnews.io/api/v4/search"
    since = (datetime.now(timezone.utc) - timedelta(hours=GNEWS_LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "q": topic,
        "lang": "en",
        "max": GNEWS_MAX_ARTICLES,
        "sortby": "publishedAt",
        "from": since,
        "token": GNEWS_API_KEY,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data.get("articles", [])


def fetch_news_google_rss(topic: str) -> list[dict]:
    """Fetch latest articles on a topic from Google News RSS (no API key needed).

    Used as a fallback when GNews returns nothing — Google News RSS tends to
    be indexed far more currently, at the cost of slightly messier titles
    (often suffixed with " - Source Name").

    Returns articles in the same shape as fetch_news_gnews() (title, url,
    publishedAt, description) so downstream code doesn't need to care which
    source it came from.
    """
    query = quote(topic)
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    articles = []
    for item in root.findall(".//item")[:GNEWS_MAX_ARTICLES]:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        description = item.findtext("description") or ""

        published_iso = None
        pub_date_raw = item.findtext("pubDate")
        if pub_date_raw:
            try:
                dt = parsedate_to_datetime(pub_date_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                published_iso = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (TypeError, ValueError):
                published_iso = None

        articles.append({
            "title": title,
            "url": link,
            "publishedAt": published_iso,
            "description": description,
        })

    return articles


def _sort_by_newest(articles: list[dict]) -> list[dict]:
    """Sort articles newest-first by publishedAt, regardless of source.

    Articles with a missing or unparseable date are sorted to the end
    rather than crashing or being dropped.
    """
    def sort_key(article: dict):
        published_at = article.get("publishedAt")
        if not published_at:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            return datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    return sorted(articles, key=sort_key, reverse=True)


def fetch_news(topic: str) -> tuple[list[dict], str]:
    """Fetch news for a topic, trying GNews first and falling back to Google
    News RSS if GNews returns nothing. Results are always sorted newest-first,
    regardless of the order returned by the source API.

    Returns (articles, source_label) so the caller/logs can tell which
    source actually supplied the results.
    """
    try:
        articles = fetch_news_gnews(topic)
    except requests.RequestException as e:
        print(f"GNews request failed ({e}), falling back to Google News RSS", file=sys.stderr)
        articles = []

    if articles:
        return _sort_by_newest(articles), "GNews"

    print("GNews returned no articles, falling back to Google News RSS...")
    try:
        articles = fetch_news_google_rss(topic)
    except (requests.RequestException, ET.ParseError) as e:
        print(f"Google News RSS fallback also failed: {e}", file=sys.stderr)
        articles = []

    return _sort_by_newest(articles), ("Google News" if articles else "none")


def summarize_articles(topic: str, articles: list[dict]) -> list[str]:
    """Use Gemini to generate one punchy summary sentence per article.

    Returns a list of plain-text summaries, in the same order as `articles`.
    URLs are NOT generated by the model — they're taken directly from the
    GNews data in build_digest() to avoid any risk of mismatched/incorrect links.
    """
    if not articles:
        return []

    articles_text = "\n\n".join(
        f"{i+1}. Title: {a['title']}\nDescription: {a.get('description', '')}"
        for i, a in enumerate(articles[:DIGEST_ARTICLE_COUNT])
    )

    prompt = f"""You are writing a short daily news digest about "{topic}".

Below are today's raw articles, numbered. For each one, write exactly ONE punchy,
informative sentence summarizing it (not just rephrasing the headline - pull out
the key fact).

Respond with ONLY a JSON array of strings, one per article, in the same order,
with no markdown formatting, no code fences, and no extra commentary. Example:
["Summary of article 1.", "Summary of article 2."]

Articles:
{articles_text}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

    # Strip accidental code fences, just in case the model adds them
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.split("\n", 1)[-1] if raw_text.lower().startswith("json") else raw_text

    try:
        summaries = json.loads(raw_text)
    except json.JSONDecodeError:
        print(f"Warning: could not parse Gemini JSON output, falling back to raw text:\n{raw_text}", file=sys.stderr)
        # Fall back: one summary per line, in order
        summaries = [line.strip("- ").strip() for line in raw_text.splitlines() if line.strip()]

    return summaries


def build_digest(topic: str, articles: list[dict], summaries: list[str], source: str = "GNews") -> str:
    """Assemble the final Telegram message with today's date, each article's
    publish date, and real article URLs."""
    date_str = datetime.now(SGT).strftime("%d %B %Y")
    header = f"📰 *Daily {topic.title()} Digest* — {date_str}"

    if not articles:
        return (
            f"{header}\n\n"
            f"No new articles found for \"{topic}\" (checked both GNews and Google News) "
            f"— nothing fresh to report today."
        )

    lines = [header]
    if source == "Google News":
        lines.append("_(via Google News, as GNews had nothing today)_")
    lines.append("")

    for i, article in enumerate(articles[:DIGEST_ARTICLE_COUNT]):
        summary = summaries[i] if i < len(summaries) else article["title"]
        published_str = _format_published_date(article.get("publishedAt"))
        lines.append(f"{i+1}. [{summary}]({article['url']})")
        lines.append(f"   🗓 {published_str}")
        lines.append("")  # blank line between articles

    return "\n".join(lines).rstrip()


def _format_published_date(published_at: str | None) -> str:
    """Convert GNews' publishedAt (ISO 8601 UTC) into a readable SGT date/time."""
    if not published_at:
        return "Date unknown"
    try:
        dt_utc = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        dt_sgt = dt_utc.astimezone(SGT)
        return dt_sgt.strftime("%d %b %Y, %I:%M%p SGT")
    except ValueError:
        return "Date unknown"


def send_to_telegram(text: str) -> None:
    """Send the digest to the configured Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload, timeout=20)
    if not resp.ok:
        print(f"Telegram API error: {resp.status_code} {resp.text}", file=sys.stderr)
        resp.raise_for_status()


def main():
    print(f"Fetching news for topic: {TOPIC}")
    articles, source = fetch_news(TOPIC)
    print(f"Found {len(articles)} articles (source: {source})")

    summaries = summarize_articles(TOPIC, articles)
    digest = build_digest(TOPIC, articles, summaries, source)
    print("Digest generated:\n", digest)

    send_to_telegram(digest)
    print("Sent to Telegram successfully.")


if __name__ == "__main__":
    main()
