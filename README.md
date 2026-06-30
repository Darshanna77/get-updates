# Pulse Monitor Bot

A personal Telegram bot that monitors multiple data sources and sends real-time alerts.

## Features

- Monitor multiple entities across different sources
- Alert **multiple Telegram users** with new bulletins
- Alert on new bulletins and activities
- **Configurable polling interval** (5-60 minutes recommended)
- Prevent duplicate alerts with local SQLite storage
- Per-user independent tracking registries
- Easy-to-use Telegram commands

## Bot Commands

- `/add TAG [SOURCE]` - Add an entity to your registry (e.g. `/add INFY SRCA`)
- `/remove TAG [SOURCE]` - Remove an entity from your registry
- `/list` - View your current registry
- `/search QUERY` - Search for entities
- `/latestBul TAG [SOURCE]` - Latest 5 bulletins for a tag
- `/latestEvt TAG [SOURCE]` - Activity summary (last 10 years)
- `/check` - Manually trigger a check
- `/status` - View bot status

All commands are case-insensitive.

## Setup Instructions

### Prerequisites

- Python 3.8+
- GitHub account
- Telegram account with a bot token

### Step 1: Get Telegram Bot Token

1. Open Telegram and search for `@BotFather`
2. Send `/start` and then `/newbot`
3. Follow the prompts to create a new bot
4. Copy the bot token provided

### Step 2: Get Your Chat ID

1. Search for `@getidsbot` on Telegram
2. Send `/start` to get your chat ID

### Step 3: Local Setup (Optional for Testing)

```bash
git clone <your-repo-url>
cd pulse-monitor

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_IDS=your_chat_id_here
EOF

python run_monitor.py
```

### Step 4: GitHub Actions Deployment

1. Push your code to a GitHub repository
2. Add secrets to GitHub:
   - Go to **Settings → Secrets and variables → Actions**
   - Add `TELEGRAM_BOT_TOKEN`
   - Add `TELEGRAM_CHAT_IDS` (comma-separated if multiple chat IDs)
3. The bot will run automatically via GitHub Actions every 5 minutes

### Step 5: Reliable 5-Minute External Trigger (Recommended)

GitHub scheduled workflows can be delayed under load. For tighter 5-minute reliability, trigger the workflow externally using `repository_dispatch`.

1. Create a GitHub fine-grained Personal Access Token with **Contents: Read and write** on this repo.
2. In [cron-job.org](https://cron-job.org), create a job to run every 5 minutes:
    - **Method:** `POST`
    - **URL:** `https://api.github.com/repos/<OWNER>/<REPO>/dispatches`
    - **Headers:**
       - `Accept: application/vnd.github+json`
       - `Authorization: Bearer <YOUR_TOKEN>`
       - `X-GitHub-Api-Version: 2022-11-28`
       - `Content-Type: application/json`
    - **Body (raw JSON):**

```json
{"event_type": "poll_tick"}
```

Expected response: HTTP 204 (success).

## Project Structure

```
pulse-monitor/
├── run_monitor.py         # Main polling script (GitHub Actions)
├── data_fetcher.py        # Data fetching from sources
├── database.py            # SQLite database operations
├── config.py              # Configuration
├── bot.py                 # Telegram bot handler
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variables template
├── pulse.db               # Local database (tracked in git)
└── .github/workflows/     # GitHub Actions workflows
```

## Security

- Only chat IDs listed in `TELEGRAM_CHAT_IDS` secret can use the bot or receive alerts
- Secrets are never exposed in logs or code
- Each user maintains their own independent registry
