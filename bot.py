"""Pulse Monitor - Telegram Bot."""
import logging
import asyncio
from typing import Dict, List
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telegram.error import TelegramError

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS, POLL_INTERVAL
from database import Database
from data_fetcher import DataFetcher

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize components
db = Database()
fetcher = DataFetcher()

# Conversation states
SEARCH_QUERY, CONFIRM_SELECTION, REMOVE_SELECTION, SELECT_EXCHANGE = range(4)

# Store user conversations
user_search_results: Dict[int, List] = {}
user_search_query: Dict[int, str] = {}


async def send_to_all_chats(context: ContextTypes.DEFAULT_TYPE, text: str, parse_mode: str = "Markdown"):
    """Send message to all configured chat IDs."""
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode
            )
        except TelegramError as e:
            logger.error(f"Failed to send message to chat {chat_id}: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler."""
    welcome_text = """
🤖 *SRCA Corporate Announcements Monitor*

I monitor SRCA corporate announcements and actions for you.

*Available Commands:*
📌 /add - Add company to registry
❌ /remove - Remove company from registry
📋 /list - View your registry
🔍 /search - Search for SRCA companies
✅ /check - Manually check for new announcements/actions
📊 /status - View bot status

Use /help for detailed information.
    """
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler."""
    help_text = """
*Commands Help:*

🔍 **/search <company_name>**
Find SRCA companies by name or symbol
Example: /search Infosys

📌 **/add**
Add a company to your registry
(You'll select from search results)

📋 **/list**
View all companies in your registry

❌ **/remove**
Remove a company from registry

✅ **/check**
Manually check for new announcements and corporate actions

📊 **/status**
View bot status and last check time

*How to add a company:*
1. Use /search to find the company
2. Select from numbered list
3. Confirm before adding
4. Company is added to registry

The bot automatically checks every 5 minutes for new announcements.
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search command handler."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /search <company_name_or_symbol>\n"
            "Example: /search Infosys"
        )
        return SEARCH_QUERY

    query = " ".join(context.args)
    results = fetcher.search_all_exchanges(query)

    if not results:
        await update.message.reply_text(
            f"❌ No companies found matching '{query}'"
        )
        return ConversationHandler.END

    # Store results for this user
    user_id = update.message.from_user.id
    user_search_results[user_id] = results
    user_search_query[user_id] = query

    # Build message with numbered list
    response = f"🔍 *Found {len(results)} companies matching '{query}':*\n\n"
    for idx, company in enumerate(results, 1):
        in_watchlist = "✓" if db.is_in_watchlist(company["symbol"], company["exchange"]) else " "
        response += f"{idx}. [{in_watchlist}] {company['symbol']} ({company['exchange']}) - {company['name']}\n"

    response += "\n_Use /add to add one to your watchlist_"

    await update.message.reply_text(response, parse_mode="Markdown")


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add command handler - allows selecting from search results."""
    user_id = update.message.from_user.id

    if user_id not in user_search_results:
        await update.message.reply_text(
            "No search results to select from. Use /search first.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    results = user_search_results[user_id]

    # Create numbered buttons for selection
    keyboard = []
    for idx, company in enumerate(results, 1):
        button_text = f"{idx}. {company['symbol']} - {company['name']}"
        callback_data = f"add_{idx - 1}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Select company to add to registry:",
        reply_markup=reply_markup
    )

    return CONFIRM_SELECTION


async def confirm_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm adding company to registry."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if user_id not in user_search_results:
        await query.edit_message_text("Session expired. Use /search again.")
        return ConversationHandler.END

    # Extract index from callback data
    callback_data = query.data
    idx = int(callback_data.split("_")[1])
    results = user_search_results[user_id]

    if idx >= len(results):
        await query.edit_message_text("Invalid selection")
        return ConversationHandler.END

    selected = results[idx]

    # Confirm before adding
    confirm_message = (
        f"Please confirm adding this company to your registry:\n\n"
        f"🏢 *Symbol:* {selected['symbol']}\n"
        f"🏛️  *Exchange:* {selected['exchange']}\n"
        f"🏛️  *Name:* {selected['name']}\n\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_add_{idx}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        confirm_message,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

    return CONFIRM_SELECTION


async def process_confirm_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process confirmed add."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if user_id not in user_search_results:
        await query.edit_message_text("Session expired.")
        return ConversationHandler.END

    callback_data = query.data
    idx = int(callback_data.split("_")[2])
    results = user_search_results[user_id]
    selected = results[idx]

    # Add to registry
    success = db.add_to_watchlist(selected["symbol"], selected["name"], selected["exchange"])

    if success:
        await query.edit_message_text(
            f"✅ Added {selected['symbol']} ({selected['exchange']}) to registry!",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"⚠️  {selected['symbol']} ({selected['exchange']}) is already in your registry",
            parse_mode="Markdown"
        )

    # Clean up
    if user_id in user_search_results:
        del user_search_results[user_id]
    if user_id in user_search_query:
        del user_search_query[user_id]

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel callback handler."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Cancelled.")
    return ConversationHandler.END


async def list_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List command handler."""
    registry = db.get_watchlist()

    if not registry:
        await update.message.reply_text(
            "📋 Your registry is empty.\n"
            "Use /search and /add to add companies.",
            parse_mode="Markdown"
        )
        return

    response = "📋 *Your Registry:*\n\n"
    for idx, company in enumerate(registry, 1):
        response += f"{idx}. {company['symbol']} ({company['exchange']}) - {company['name']}\n"

    response += f"\n_Total: {len(registry)} companies_"
    await update.message.reply_text(response, parse_mode="Markdown")


async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove command handler."""
    registry = db.get_watchlist()

    if not registry:
        await update.message.reply_text(
            "Your registry is empty. Nothing to remove.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Create numbered buttons for selection
    keyboard = []
    for idx, company in enumerate(registry, 1):
        button_text = f"{idx}. {company['symbol']} - {company['name']}"
        callback_data = f"remove_{idx - 1}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Select company to remove from registry:",
        reply_markup=reply_markup
    )

    # Store registry for this user
    user_id = update.message.from_user.id
    user_search_results[user_id] = registry

    return REMOVE_SELECTION


async def confirm_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm removing company from registry."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if user_id not in user_search_results:
        await query.edit_message_text("Session expired.")
        return ConversationHandler.END

    callback_data = query.data
    idx = int(callback_data.split("_")[1])
    registry = user_search_results[user_id]

    if idx >= len(registry):
        await query.edit_message_text("Invalid selection")
        return ConversationHandler.END

    selected = registry[idx]

    # Confirm before removing
    confirm_message = (
        f"Please confirm removing this company:\n\n"
        f"🏢 *Symbol:* {selected['symbol']}\n"
        f"🏛️  *Exchange:* {selected['exchange']}\n"
        f"🏛️  *Name:* {selected['name']}\n\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_remove_{idx}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        confirm_message,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

    return REMOVE_SELECTION


async def process_confirm_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process confirmed remove."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if user_id not in user_search_results:
        await query.edit_message_text("Session expired.")
        return ConversationHandler.END

    callback_data = query.data
    idx = int(callback_data.split("_")[2])
    registry = user_search_results[user_id]
    selected = registry[idx]

    # Remove from registry
    success = fetcher.validate_tag(selected["symbol"], selected["exchange"])

    if success:
        await query.edit_message_text(
            f"✅ Removed {selected['symbol']} ({selected['exchange']}) from registry!",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"❌ Could not remove {selected['symbol']}",
            parse_mode="Markdown"
        )

    # Clean up
    if user_id in user_search_results:
        del user_search_results[user_id]

    return ConversationHandler.END


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual check command."""
    await update.message.reply_text(
        "⏳ Checking for new announcements and corporate actions...",
        parse_mode="Markdown"
    )

    # Run the check
    results = await poll_announcements(context)

    if results["total_checked"] == 0:
        await update.message.reply_text(
            "📭 Your registry is empty. Use /add to add companies.",
            parse_mode="Markdown"
        )
    else:
        message = (
            f"✅ Check completed!\n\n"
            f"📊 Companies checked: {results['total_checked']}\n"
            f"📢 New announcements: {results['announcements']}\n"
            f"💼 New corporate actions: {results['corporate_actions']}\n"
        )
        await update.message.reply_text(message, parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status command."""
    registry = db.get_watchlist()
    last_check = context.bot_data.get("last_check", "Never")

    status_message = (
        f"📊 *Bot Status:*\n\n"
        f"📋 Companies in registry: {len(registry)}\n"
        f"⏰ Last check: {last_check}\n"
        f"🔄 Poll interval: {POLL_INTERVAL} seconds (5 minutes)\n"
        f"✅ Bot is {'running' if context.bot_data.get('running', False) else 'idle'}\n"
    )
    await update.message.reply_text(status_message, parse_mode="Markdown")


async def poll_announcements(context: ContextTypes.DEFAULT_TYPE) -> Dict:
    """Poll announcements and corporate actions."""
    results = {
        "total_checked": 0,
        "announcements": 0,
        "corporate_actions": 0,
    }

    registry = db.get_watchlist()
    results["total_checked"] = len(registry)

    if not registry:
        return results

    logger.info(f"Polling {len(registry)} companies...")

    for company in registry:
        symbol = company["symbol"]
        exchange = company["exchange"]

        # Check announcements
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
                results["announcements"] += 1
                # Send notification
                message = (
                    f"📢 *New Announcement*\n\n"
                    f"🏢 Company: {company['name']} ({symbol})\n"
                    f"🏛️  Exchange: {exchange}\n"
                    f"📄 Title: {announcement.get('title', 'N/A')}\n"
                    f"📅 Date: {announcement.get('date', 'N/A')}\n"
                )
                await send_to_all_chats(context, message)

        # Check corporate actions
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
                results["corporate_actions"] += 1
                # Send notification
                message = (
                    f"💼 *New Corporate Action*\n\n"
                    f"🏢 Company: {company['name']} ({symbol})\n"
                    f"🏛️  Exchange: {exchange}\n"
                    f"📝 Type: {action.get('type', 'N/A')}\n"
                    f"📄 Title: {action.get('title', 'N/A')}\n"
                    f"📅 Date: {action.get('date', 'N/A')}\n"
                )
                await send_to_all_chats(context, message)

    # Update last check time
    context.bot_data["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return results


async def poll_task(context: ContextTypes.DEFAULT_TYPE):
    """Background polling task."""
    try:
        logger.info("Running scheduled poll...")
        await poll_announcements(context)
    except Exception as e:
        logger.error(f"Polling error: {e}")


async def post_init(application: Application):
    """Initialize after bot is ready."""
    logger.info("Bot is starting...")
    context = application.context_types.context_class(application=application)
    context.bot_data = {"running": True}

    # Set up polling job
    job_queue = application.job_queue
    job_queue.run_repeating(poll_task, interval=POLL_INTERVAL, first=10)
    logger.info(f"Polling scheduled every {POLL_INTERVAL} seconds")


def main():
    """Main function."""
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_watchlist))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CommandHandler("status", status))

    # Search conversation
    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("search", search)],
        states={
            SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(search_conv_handler)

    # Add conversation
    add_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add)],
        states={
            CONFIRM_SELECTION: [
                CallbackQueryHandler(confirm_add, pattern="^add_"),
                CallbackQueryHandler(process_confirm_add, pattern="^confirm_add_"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_conv_handler)

    # Remove conversation
    remove_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("remove", remove)],
        states={
            REMOVE_SELECTION: [
                CallbackQueryHandler(confirm_remove, pattern="^remove_"),
                CallbackQueryHandler(process_confirm_remove, pattern="^confirm_remove_"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(remove_conv_handler)

    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
