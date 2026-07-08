"""
Daily Telegram News Digest Bot
------------------------------
Fetches the latest news on a topic (via GNews API), summarizes each article
into a punchy one-liner using Claude, and sends a formatted digest to a
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
import requests

# ---------- Config ----------
GNEWS_MAX_ARTICLES = 5          # how many articles to pull from GNews
DIGEST_ARTICLE_COUNT = 5        # how many to include in the final digest (short format)
GEMINI_MODEL = "gemini-2.5-flash"  # fast, free-tier-friendly model

TOPIC = os.environ.get("NEWS_TOPIC", "technology")
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GNEWS_API_KEY = os.environ["GNEWS_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]


def fetch_news(topic: str) -> list[dict]:
    """Fetch latest articles on a topic from GNews."""
    url = "https://gnews.io/api/v4/search"
    params = {
        "q": topic,
        "lang": "en",
        "max": GNEWS_MAX_ARTICLES,
        "sortby": "publishedAt",
        "token": GNEWS_API_KEY,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data.get("articles", [])


def summarize_articles(topic: str, articles: list[dict]) -> str:
    """Use Gemini to turn raw articles into a short digest (one line each)."""
    if not articles:
        return f"No news found today for topic: {topic}"

    articles_text = "\n\n".join(
        f"Title: {a['title']}\nDescription: {a.get('description', '')}\nURL: {a['url']}"
        for a in articles[:DIGEST_ARTICLE_COUNT]
    )

    prompt = f"""You are writing a short daily news digest for a Telegram group about "{topic}".

Below are today's raw articles. For each one, write exactly ONE punchy, informative
sentence summarizing it (not just rephrasing the headline - pull out the key fact).
Format your entire response using Telegram Markdown like this, with no extra commentary:

📰 *Daily {topic.title()} Digest*

1. [One-line summary here]({{url}})
2. [One-line summary here]({{url}})
...

Articles:
{articles_text}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


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
    articles = fetch_news(TOPIC)
    print(f"Found {len(articles)} articles")

    digest = summarize_articles(TOPIC, articles)
    print("Digest generated:\n", digest)

    send_to_telegram(digest)
    print("Sent to Telegram successfully.")


if __name__ == "__main__":
    main()
