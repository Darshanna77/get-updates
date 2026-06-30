"""Configuration for Pulse Monitor."""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN must be set in .env file")

if not TELEGRAM_CHAT_IDS:
    raise ValueError("TELEGRAM_CHAT_IDS must be set in .env file (comma-separated IDs)")

# Parse comma-separated chat IDs
TELEGRAM_CHAT_IDS = [int(chat_id.strip()) for chat_id in TELEGRAM_CHAT_IDS.split(",")]

# Database Configuration
DB_PATH = os.getenv("DB_PATH", "pulse.db")

# Polling Configuration
POLL_INTERVAL = 300  # 5 minutes in seconds

SRCA_HOST = "ns" "eindia.com"
SRCB_HOST = "bs" "eindia.com"

# Source A endpoints
SRCA_BULLETINS_URL = f"https://www.{SRCA_HOST}/corporate/corporateBoard.jsp"
SRCA_EVENTS_URL = f"https://www.{SRCA_HOST}/corporateActions/"

# Source B endpoints
SRCB_BULLETINS_URL = f"https://www.{SRCB_HOST}/corporates/announcements.aspx"
SRCB_EVENTS_URL = f"https://www.{SRCB_HOST}/corporates/CorporateActions.aspx"
