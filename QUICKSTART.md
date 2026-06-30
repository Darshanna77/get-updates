# Quick Start - 5 Minutes

If you want to get started immediately without reading the full guide:

## 1. Create Bot (2 min)

- Open Telegram, search `@BotFather`
- Send `/newbot`, follow prompts
- Copy the token you receive
- Search `@getidsbot`, get your chat ID (do this for each user who should get alerts)

## 2. Create GitHub Repo (1 min)

- Go to https://github.com/new
- Name it `pulse-monitor`
- **Check "Private"**
- Create

## 3. Add Secrets (1 min)

- Go to your repo → Settings → Secrets → Actions
- Add `TELEGRAM_BOT_TOKEN` = your token
- Add `TELEGRAM_CHAT_IDS` = comma-separated chat IDs
  - Single user: `123456789`
  - Multiple: `123456789,987654321`

## 4. Push Code (1 min)

```bash
git clone https://github.com/YOUR_USERNAME/pulse-monitor.git
cd pulse-monitor
# Copy all project files here
git add .
git commit -m "Initial setup"
git push origin main
```

## 5. Test (manual trigger)

- Actions tab → "SRCA Bot - Poll Updates"
- Click "Run workflow"
- Bot now active and will run every 5 minutes!

## Use in Telegram

```
/search Infosys   # Find entity (searches SRCA & SRCB)
/add              # Add to registry (select - shows SRCA or SRCB)
/list             # View registry (shows source for each)
/check            # Manually check now
```

---

**Full guide:** See DEPLOYMENT.md
