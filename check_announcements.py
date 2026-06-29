"""Standalone polling script for GitHub Actions."""
import asyncio
import logging
from database import Database
from nse_fetcher import StockFetcher
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS
from telegram import Bot
from datetime import datetime

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def send_to_all_chats(bot: Bot, text: str):
    """Send message to all configured chat IDs."""
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send message to chat {chat_id}: {e}")


async def check_announcements():
    """Check for new announcements and send alerts."""
    db = Database()
    fetcher = StockFetcher()
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    watchlist = db.get_watchlist()
    logger.info(f"Checking {len(watchlist)} companies...")

    announcements_count = 0
    actions_count = 0

    for company in watchlist:
        symbol = company["symbol"]
        exchange = company["exchange"]
        logger.info(f"Checking {symbol} ({exchange})...")

        # Check announcements
        try:
            announcements = fetcher.get_announcements(symbol, exchange)
            for announcement in announcements:
                marked = db.mark_announcement_processed(
                    symbol,
                    exchange,
                    announcement.get("id", ""),
                    announcement.get("title", ""),
                    announcement.get("date", "")
                )
                if marked:
                    announcements_count += 1
                    message = (
                        f"📢 *New Announcement*\n\n"
                        f"🏢 Company: {company['name']} ({symbol})\n"
                        f"🏛️  Exchange: {exchange}\n"
                        f"📄 Title: {announcement.get('title', 'N/A')}\n"
                        f"📅 Date: {announcement.get('date', 'N/A')}\n"
                    )
                    await send_to_all_chats(bot, message)
        except Exception as e:
            logger.error(f"Error checking announcements for {symbol} ({exchange}): {e}")

        # Check corporate actions
        try:
            actions = fetcher.get_corporate_actions(symbol, exchange)
            for action in actions:
                marked = db.mark_corporate_action_processed(
                    symbol,
                    exchange,
                    action.get("id", ""),
                    action.get("type", ""),
                    action.get("title", ""),
                    action.get("date", "")
                )
                if marked:
                    actions_count += 1
                    message = (
                        f"💼 *New Corporate Action*\n\n"
                        f"🏢 Company: {company['name']} ({symbol})\n"
                        f"🏛️  Exchange: {exchange}\n"
                        f"📝 Type: {action.get('type', 'N/A')}\n"
                        f"📄 Title: {action.get('title', 'N/A')}\n"
                        f"📅 Date: {action.get('date', 'N/A')}\n"
                    )
                    await send_to_all_chats(bot, message)
        except Exception as e:
            logger.error(f"Error checking corporate actions for {symbol} ({exchange}): {e}")

    # Send summary
    summary = (
        f"✅ Check completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"📊 Companies checked: {len(watchlist)}\n"
        f"📢 New announcements: {announcements_count}\n"
        f"💼 New corporate actions: {actions_count}\n"
    )
    logger.info(summary)
    await send_to_all_chats(bot, summary)


if __name__ == "__main__":
    asyncio.run(check_announcements())
