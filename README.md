# Telegram Daily News Digest Bot

Sends a short, Claude-summarized news digest to a Telegram group every day at
**9:00 AM Singapore Time**. The topic is easy to change without touching code.

## How it works
1. GitHub Actions triggers `news_bot.py` on a daily cron schedule.
2. The script pulls the latest articles on your topic from **GNews**.
3. **Claude** (Anthropic API) turns them into 5 punchy one-line summaries.
4. The digest is sent to your Telegram group via the **Telegram Bot API**.

---

## Setup steps

### 1. Create your Telegram bot
1. Open Telegram, message **@BotFather**.
2. Send `/newbot` and follow the prompts.
3. Copy the token it gives you (looks like `123456789:ABCdef...`).

### 2. Get your group's chat ID
1. Add your bot to the target group.
2. Send any message in the group.
3. Visit this URL in your browser (replace `<TOKEN>`):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Find `"chat":{"id": ...}` in the response — group IDs are usually negative
   (e.g. `-1001234567890`). That's your `TELEGRAM_CHAT_ID`.

### 3. Get a GNews API key
- Sign up free at https://gnews.io (free tier: ~100 requests/day).

### 4. Get a Gemini API key (free)
- From https://aistudio.google.com/apikey (used to generate the summaries).
- Google AI Studio's free tier is generous enough for one digest a day — no
  billing required for this use case.

### 5. Push this folder to a new GitHub repo
```bash
cd telegram-news-bot
git init
git add .
git commit -m "Initial commit"
git remote add origin <your-repo-url>
git push -u origin main
```

### 6. Add your secrets to the GitHub repo
Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**,
and add each of these:

| Secret name          | Value                              |
|-----------------------|-------------------------------------|
| `TELEGRAM_BOT_TOKEN`  | from step 1                        |
| `TELEGRAM_CHAT_ID`    | from step 2                        |
| `GNEWS_API_KEY`       | from step 3                        |
| `GEMINI_API_KEY`      | from step 4                        |

### 7. Set your topic
Go to **Settings → Secrets and variables → Actions → Variables tab** and add:

| Variable name | Value                                    |
|-----------------|-------------------------------------------|
| `NEWS_TOPIC`   | e.g. `artificial intelligence`, `Singapore economy`, `climate change` |

You can change this any time — no code changes or redeploy needed.

### 8. Test it
Go to the **Actions** tab in your repo → **Daily News Digest** → **Run workflow**.
You can optionally type a one-off topic override in the manual trigger box.
Check your Telegram group for the message.

Once confirmed working, it will run automatically every day at 9:00 AM SGT.

---

## Running locally (optional, for testing)
```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export GNEWS_API_KEY="..."
export GEMINI_API_KEY="..."
export NEWS_TOPIC="artificial intelligence"
python news_bot.py
```

## Customizing
- **Digest length**: edit `DIGEST_ARTICLE_COUNT` in `news_bot.py` (currently 5).
- **Send time**: edit the cron line in `.github/workflows/daily_digest.yml`.
  GitHub Actions cron is in UTC — 9:00 AM SGT is `1:00 AM UTC` (`0 1 * * *`).
- **Multiple topics**: you can duplicate the workflow step with different
  `NEWS_TOPIC` values, or extend the script to loop over a list of topics.

## Notes
- GitHub Actions free tier includes plenty of minutes for a job this small
  (runs in well under a minute, once daily).
- Cron schedules on GitHub Actions can occasionally fire a few minutes late
  during high-load periods — this is a GitHub platform limitation, not a bug
  in this script.
