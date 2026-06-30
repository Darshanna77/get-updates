# NSE & BSE Bot - Corporate Announcements Monitor

A personal Telegram bot that monitors NSE (National Stock Exchange) and BSE (Bombay Stock Exchange) Corporate Announcements and Corporate Actions.

## Features

- Monitor multiple NSE and BSE listed companies
- Alert **multiple Telegram users** with announcements
- Alert on new corporate announcements
- Alert on new corporate actions
- **Configurable polling interval** (5-60 minutes recommended)
- Prevent duplicate alerts with local SQLite storage
- Easy-to-use Telegram commands

## Bot Commands

- `/add` - Add a company to watchlist
- `/remove` - Remove a company from watchlist
- `/list` - View current watchlist
- `/search` - Search for NSE companies
- `/latestAnn` - Latest 5 announcements for a symbol
- `/latestAct` - Corporate actions summary (last 10 years)
- `/check` - Manually check for new announcements/actions
- `/status` - View bot status

All commands are case-insensitive, so `/ADD`, `/Add`, and `/add` work the same.

## Setup Instructions

### Prerequisites

- Python 3.8+
- GitHub account with private repository
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
# Clone the repository
git clone <your-repo-url>
cd nse-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_IDS=your_chat_id_here
EOF

# Run the bot
python bot.py
```

### Step 4: GitHub Actions Deployment

1. Create a private GitHub repository
2. Push your code to the repository
3. Add secrets to GitHub:
   - Go to Settings → Secrets and variables → Actions
   - Add `TELEGRAM_BOT_TOKEN`
   - Add `TELEGRAM_CHAT_IDS` (comma-separated if multiple chat IDs)
4. The bot will run automatically via GitHub Actions

### Step 5: Reliable 5-Minute Trigger (Recommended)

GitHub scheduled workflows can be delayed under load. For tighter 5-minute reliability, trigger the workflow externally using `repository_dispatch`.

1. Create a GitHub Personal Access Token (classic or fine-grained) with repository workflow trigger rights.
    - Fine-grained token (recommended): repository access to this repo, with Actions `Read and write` and Contents `Read`.
2. Create a secret in your external scheduler named `GH_DISPATCH_TOKEN` with that token.
3. In a scheduler like cron-job.org, set a job to run every 5 minutes with:
    - Method: `POST`
    - URL: `https://api.github.com/repos/<OWNER>/<REPO>/dispatches`
    - Headers:
       - `Accept: application/vnd.github+json`
       - `Authorization: Bearer <GH_DISPATCH_TOKEN>`
       - `X-GitHub-Api-Version: 2022-11-28`
    - Body:

```json
{
   "event_type": "poll_tick"
}
```

This repository is already configured to accept `poll_tick` dispatch events in the workflow.

## Project Structure

```
nse-bot/
├── bot.py                 # Main bot logic
├── config.py              # Configuration (includes polling interval)
├── database.py            # SQLite database operations
├── nse_fetcher.py        # NSE & BSE data fetching
├── check_announcements.py # GitHub Actions polling script
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── DEPLOYMENT.md         # Complete deployment guide
├── POLLING_ANALYSIS.md   # Detailed polling interval analysis ⭐
├── POLLING_QUICK_REFERENCE.md # Quick polling guide ⭐
├── README.md             # This file
└── .github/workflows/    # GitHub Actions workflows
```

**⭐ New: See [POLLING_ANALYSIS.md](POLLING_ANALYSIS.md) for detailed polling interval recommendations!**

## Database Schema

### watchlist
- id: Primary key
- symbol: Stock symbol (NSE or BSE)
- company_name: Company name
- exchange: NSE or BSE
- added_date: When added

### processed_announcements
- Stores announcement IDs to prevent duplicates (per exchange)

### processed_corporate_actions
- Stores corporate action IDs to prevent duplicates (per exchange)

## NSE & BSE Symbols

The bot uses stock symbols for company identification. Examples:

**NSE:**
- INFY → Infosys
- TCS → Tata Consultancy Services
- WIPRO → Wipro
- HDFC → HDFC Bank

**BSE:**
- SENSEX → BSE Sensex 50
- RELIANCE → Reliance Industries
- ITC → ITC Limited
- SBIN → State Bank of India

## Troubleshooting

- **Bot not sending messages**: Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_IDS`
- **No announcements fetched**: Verify NSE website availability
- **Duplicate alerts**: Check database records in `nse_bot.db`

## Contributing

This is a personal project, but feel free to fork and modify for your needs.

## License

Private repository - for personal use only.
