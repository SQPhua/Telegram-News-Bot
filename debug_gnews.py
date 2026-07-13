"""
GNews Debug/Test Script
------------------------
Run this locally (or as a one-off GitHub Actions job) to see exactly what
GNews returns for several topic wording and time-window variations. Useful
for diagnosing "no articles found" issues without guessing.

Usage:
    export GNEWS_API_KEY="your_key_here"
    python debug_gnews.py
"""

import os
import requests
from datetime import datetime, timezone, timedelta

GNEWS_API_KEY = os.environ["GNEWS_API_KEY"]

# Test cases: (label, query, hours_back)
TEST_CASES = [
    ("Exact phrase, 24h",  "Strait of Hormuz mines", 24),
    ("Exact phrase, 48h",  "Strait of Hormuz mines", 48),
    ("Exact phrase, 7d",   "Strait of Hormuz mines", 24 * 7),
    ("Broader (no 'mines'), 48h", "Strait of Hormuz", 48),
    ("Broader (no 'mines'), 7d",  "Strait of Hormuz", 24 * 7),
    ("'mining' instead of 'mines', 48h", "Strait of Hormuz mining", 48),
    ("No time filter at all", "Strait of Hormuz mines", None),
]


def run_test(label: str, query: str, hours_back: int | None):
    url = "https://gnews.io/api/v4/search"
    params = {
        "q": query,
        "lang": "en",
        "max": 5,
        "sortby": "publishedAt",
        "token": GNEWS_API_KEY,
    }
    if hours_back is not None:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params["from"] = since

    resp = requests.get(url, params=params, timeout=20)
    print(f"\n=== {label} ===")
    print(f"Query: '{query}' | Window: {hours_back}h back" if hours_back else f"Query: '{query}' | No window")
    print(f"HTTP status: {resp.status_code}")

    if not resp.ok:
        print(f"Error response: {resp.text}")
        return

    data = resp.json()
    articles = data.get("articles", [])
    print(f"Articles found: {len(articles)} (totalArticles reported: {data.get('totalArticles', '?')})")
    for a in articles[:3]:
        print(f"  - [{a.get('publishedAt')}] {a.get('title')}")


def main():
    for label, query, hours_back in TEST_CASES:
        run_test(label, query, hours_back)


if __name__ == "__main__":
    main()
