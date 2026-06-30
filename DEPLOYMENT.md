# SRCA & SRCB Bot - Complete Deployment Guide

This guide will walk you through setting up the SRCA & SRCB Corporate Announcements Monitor bot, step by step.

## Prerequisites Checklist

- [ ] GitHub account (free)
- [ ] Telegram account
- [ ] Python 3.8+ (for local testing)
- [ ] Git installed

---

## STEP 1: Create Telegram Bot Token

### 1.1 Get Bot Token from BotFather

1. Open Telegram and search for `@BotFather`
2. Send message `/start`
3. Send message `/newbot`
4. Follow the prompts:
   - Choose a name (e.g., "SRCA & SRCB Announcements Monitor")
   - Choose a username (e.g., "pulse_monitor_bot")
5. BotFather will send you a token like: `123456789:ABCDEFGHIjklmnopQRSTUvwxyz`
6. **Save this token** - you'll need it

### 1.2 Get Your Chat ID(s)

You can send alerts to one or multiple Telegram chat IDs!

**For each person who should receive alerts:**

1. In Telegram, search for `@getidsbot`
2. Send message `/start`
3. It will reply with your chat ID (a number)
4. **Save all chat IDs** - you'll need them

**Example:**
- User 1 Chat ID: `123456789`
- User 2 Chat ID: `987654321`
- User 3 Chat ID: `555555555`

---

## STEP 2: Create GitHub Repository

### 2.1 Create Private Repository

1. Go to https://github.com/new
2. Fill in details:
   - Repository name: `pulse-monitor` (or any name)
   - Description: "Personal SRCA & SRCB Corporate Announcements Monitor"
   - **Select "Private"**
   - Initialize with README
3. Click "Create repository"

### 2.2 Clone Repository Locally

```bash
git clone https://github.com/YOUR_USERNAME/pulse-monitor.git
cd pulse-monitor
```

---

## STEP 3: Add Bot Code to Repository

1. Copy all files from this project into your cloned repository:
   - bot.py
   - run_monitor.py
   - config.py
   - database.py
   - data_fetcher.py
   - requirements.txt
   - .env.example
   - .gitignore
   - README.md
   - .github/workflows/poll-updates.yml

2. Create `.env` file (don't commit this):
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your tokens:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_from_step_1.1
   TELEGRAM_CHAT_IDS=your_chat_id_from_step_1.2
   ```
   
   For multiple users (comma-separated):
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_from_step_1.1
   TELEGRAM_CHAT_IDS=123456789,987654321,555555555
   ```

4. **Important: DO NOT commit .env file!** (Already in .gitignore)

---

## STEP 4: Test Locally (Optional)

### 4.1 Setup Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### 4.2 Install Dependencies

```bash
pip install -r requirements.txt
```

### 4.3 Test the Bot

```bash
# This will start the bot locally
python bot.py
```

Then in Telegram:
1. Find your bot (search for the username you chose)
2. Send `/start` to test if it works
3. Try `/help` to see commands
4. Send `/search Infosys` to test search

Press `Ctrl+C` to stop the bot.

---

## STEP 5: Push Code to GitHub

```bash
# Add all files
git add .

# Commit
git commit -m "Initial SRCA bot setup"

# Push to GitHub
git push origin main
```

---

## STEP 6: Add GitHub Secrets

These are securely stored secrets that GitHub Actions will use (NOT visible in code).

### 6.1 Go to Settings

1. Go to your GitHub repository
2. Click "Settings" (top menu)
3. Click "Secrets and variables" → "Actions" (left sidebar)

### 6.2 Add Secrets

Click "New repository secret" for each:

**Secret 1: TELEGRAM_BOT_TOKEN**
- Name: `TELEGRAM_BOT_TOKEN`
- Value: (paste your token from Step 1.1)
- Click "Add secret"

**Secret 2: TELEGRAM_CHAT_IDS**
- Name: `TELEGRAM_CHAT_IDS`
- Value: (comma-separated chat IDs from Step 1.2)
- Examples:
  - Single user: `123456789`
  - Multiple users: `123456789,987654321,555555555`
- Click "Add secret"

✅ Verify both secrets appear in the list

---

## STEP 7: Enable GitHub Actions

### 7.1 Check Actions Are Enabled

1. Go to your repository
2. Click "Actions" tab
3. If you see "Workflows" section, Actions is enabled ✅

### 7.2 Manually Trigger First Run

1. Click "Actions" tab
2. Click "Pulse Monitor - Poll Updates" workflow (left sidebar)
3. Click "Run workflow" → "Run workflow" (blue button)
4. Watch it run (should complete in ~30 seconds)
5. Check Telegram for confirmation message

---

## STEP 8: Setup Is Complete! 🎉

Your bot is now live and will:
- ✅ Run automatically every 5 minutes
- ✅ Monitor your registry for new bulletins
- ✅ Send you Telegram alerts
- ✅ Store processed records to avoid duplicates

## To Use the Bot:**

1. **Open Telegram** and find your bot (search the username you created)

2. **Add Companies to Registry:**
   ```
   /search Infosys
   /add
   [Select from list - shows exchange (SRCA/SRCB)]
   ```

3. **View Your Registry:**
   ```
   /list
   ```
   Shows all companies with their exchange (SRCA or SRCB)

4. **Remove Companies:**
   ```
   /remove
   [Select from list]
   ```

5. **Check Status:**
   ```
   /status
   ```

---

## Troubleshooting

### Bot Doesn't Respond

1. Check if you're messaging the correct bot
2. Verify `TELEGRAM_BOT_TOKEN` is correct in GitHub Secrets
3. Manually trigger workflow: Actions → "Pulse Monitor - Poll Updates" → "Run workflow"

### No Updates Received

1. Check your registry: `/list`
2. Add companies: `/search` then `/add`
3. Manually trigger check: `/check`

### Workflow Fails

1. Go to Actions tab
2. Click the failed workflow run
3. Look at logs for error messages
4. Common issues:
   - Missing secrets (check Step 6)
   - Invalid token (regenerate from @BotFather)
   - Wrong chat ID (verify with @getidsbot)

### Database Issues

1. The database is stored in GitHub Actions artifacts (30-day retention)
2. Each run downloads the previous database first
3. If you want to reset, delete all artifacts: Actions → (3 dots) → "Delete all artifacts"

---

## Advanced: Monitor Workflow Runs

Go to "Actions" tab in GitHub to:
- See when each check ran
- View execution logs
- Check for errors
- Manually trigger checks

---

## Modifying SRCA & SRCB Companies

The bot currently has a limited list of SRCA and SRCB companies. To add more:

1. Edit `data_fetcher.py`
2. Add SRCA entities to `SRCA_ITEMS` dictionary:
   ```python
   SRCA_ITEMS = {
       "INFY": "INFOSYS",
       "TCS": "TATA CONSULTANCY SERVICES",
       # Add more like this:
       "SBIN": "STATE BANK OF INDIA",
   }
   ```
3. Add SRCB entities to `SRCB_ITEMS` dictionary:
   ```python
      SRCB_ITEMS = {
         "IDX50": "Index Group 50",
       "RELIANCE": "RELIANCE INDUSTRIES",
       # Add more like this:
       "ITC": "ITC LIMITED",
   }
   ```
4. Push to GitHub
5. Actions will use the new list automatically

---

## Monthly Maintenance

1. **Cleanup old records:** Database automatically cleans records older than 30 days
2. **Check workflow status:** Occasionally review Actions tab
3. **Update company list:** Add new companies as needed

---

## Getting Help

For issues:
1. Check GitHub Actions logs
2. Review Telegram bot logs
3. Verify all secrets are set correctly
4. Test manually: `/check` command in Telegram

---

## Next Steps (Optional Enhancements)

- Set up notifications for specific announcement types
- Add more SRCA companies to registry
- Export registry data
- Add announcement filtering
- Create backup of database
