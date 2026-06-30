"""Standalone polling + command-handling script for GitHub Actions.

Runs every 5 minutes via GitHub Actions cron.
Each run:
  1. Processes any Telegram commands sent since last run.
  2. Checks NSE/BSE announcements for watchlisted companies.
  3. Sends alerts to all configured chat IDs.

Commands (send these to your bot on Telegram):
  /start or /help          – show command list
  /add SYMBOL [EXCHANGE]   – e.g. /add INFY NSE  (default exchange: NSE)
  /remove SYMBOL [EXCHANGE]– e.g. /remove INFY NSE
  /list                    – show current watchlist
  /search QUERY            – search NSE+BSE
    /latestAnn SYMBOL [EXCHANGE] – latest 5 announcements (5 separate messages)
    /latestAct SYMBOL [EXCHANGE] – corporate-action summary for last 10 years
  /status                  – bot status
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from database import Database
from nse_fetcher import BSE_SCRIP_CODES, StockFetcher
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS
from telegram import Bot

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def reply(bot: Bot, chat_id: int, text: str, parse_mode: Optional[str] = "Markdown"):
    """Send a message to one chat."""
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"✗ Failed to send to {chat_id}: {e}")


async def send_to_all_chats(bot: Bot, text: str, parse_mode: Optional[str] = "Markdown"):
    """Broadcast a message to every configured chat ID."""
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            logger.info(f"✓ Message sent to chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"✗ Failed to send to chat_id {chat_id}: {e}")
            logger.error("  → Make sure you have sent /start to the bot on Telegram first!")


def exchange_fallback_link(symbol: str, exchange: str) -> str:
    """Return a stable fallback page URL for the symbol/exchange."""
    if exchange.upper() == "NSE":
        return f"https://www.nseindia.com/get-quotes/equity?symbol={symbol.upper()}"
    scrip = BSE_SCRIP_CODES.get(symbol.upper(), "")
    if scrip:
        return f"https://www.bseindia.com/stock-share-price/-/-/{scrip}/"
    return "https://www.bseindia.com/"


def parse_flexible_date(date_str: str) -> Optional[datetime]:
    """Best-effort parser for exchange date formats."""
    if not date_str:
        return None
    formats = [
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%d %b %Y",
        "%d %b %Y %H:%M:%S",
        "%Y%m%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue
    return None


def classify_action_group(action: dict) -> str:
    """Group actions into meeting/discussion vs price/capital related buckets."""
    text = f"{action.get('type', '')} {action.get('title', '')}".casefold()
    meeting_keywords = (
        "meeting",
        "discussion",
        "agm",
        "egm",
        "conference call",
        "investor meet",
        "board meeting",
        "postal ballot",
    )
    if any(k in text for k in meeting_keywords):
        return "meeting"
    return "price"


async def send_chunked_lines(bot: Bot, chat_id: int, header: str, lines: list[str], chunk_limit: int = 3500):
    """Send long line lists in Telegram-safe chunks."""
    if not lines:
        await reply(bot, chat_id, f"{header}\nNone", parse_mode=None)
        return

    chunk = header + "\n"
    for line in lines:
        if len(chunk) + len(line) + 1 > chunk_limit:
            await reply(bot, chat_id, chunk, parse_mode=None)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await reply(bot, chat_id, chunk, parse_mode=None)


# ---------------------------------------------------------------------------
# Command processor  (runs at the start of every GitHub Actions job)
# ---------------------------------------------------------------------------

async def process_commands(bot: Bot, db: Database, fetcher: StockFetcher):
    """Fetch new Telegram updates and process any commands."""
    last_id = db.get_last_update_id()
    logger.info(f"Fetching Telegram updates since update_id={last_id}")

    try:
        updates = await bot.get_updates(offset=last_id + 1, timeout=5)
    except Exception as e:
        logger.error(f"Failed to get Telegram updates: {e}")
        return

    if not updates:
        logger.info("No new commands.")
        return

    logger.info(f"Processing {len(updates)} update(s)...")

    for update in updates:
        last_id = max(last_id, update.update_id)
        msg = update.message
        if not msg or not msg.text:
            continue

        chat_id = msg.chat_id
        
        # Security: Only process commands from authorized chat IDs
        if chat_id not in TELEGRAM_CHAT_IDS:
            logger.warning(f"⚠️ Unauthorized access attempt from chat_id: {chat_id}")
            await reply(bot, chat_id, "❌ You are not authorized to use this bot.")
            continue
        
        text    = msg.text.strip()
        parts   = text.split()
        # Normalize Telegram command name so all commands are case-insensitive.
        cmd     = parts[0].split("@")[0].casefold()   # strip @botname suffix

        logger.info(f"Command from {chat_id}: {text}")

        # /start  /help ───────────────────────────────────────────────────
        if cmd in ("/start", "/help"):
            await reply(bot, chat_id,
                "🤖 *NSE/BSE Announcements Bot*\n\n"
                "*Commands:*\n"
                "`/add SYMBOL [EXCHANGE]` – add to watchlist\n"
                "  _e.g. /add INFY NSE  or  /add SBIN BSE_\n\n"
                "`/remove SYMBOL [EXCHANGE]` – remove from watchlist\n"
                "  _e.g. /remove INFY NSE_\n\n"
                "`/list` – show your watchlist\n"
                "`/view` – alias for /list\n"
                "`/search QUERY` – find a company\n"
                "`/latestAnn SYMBOL [EXCHANGE]` – latest 5 announcements\n"
                "`/latestAct SYMBOL [EXCHANGE]` – 10-year action summary\n"
                "`/check` – run immediate check\n"
                "`/status` – bot status\n"
                "`/help` – show this message\n\n"
                "_Commands are processed within 5 minutes \\(next scheduled run\\)._"
            )

        # /list (/view, /veiw aliases) ───────────────────────────────────
        elif cmd in ("/list", "/view", "/veiw"):
            watchlist = db.get_watchlist()
            if not watchlist:
                await reply(bot, chat_id,
                    "📋 Your watchlist is empty\\.\n"
                    "Use `/add SYMBOL EXCHANGE` to add a company\\.\n"
                    "_Example: /add INFY NSE_"
                )
            else:
                lines = "\n".join(
                    f"{i}\\. {c['symbol']} \\({c['exchange']}\\) – {c['name']}"
                    for i, c in enumerate(watchlist, 1)
                )
                await reply(bot, chat_id,
                    f"📋 *Your Watchlist \\({len(watchlist)} companies\\):*\n\n{lines}"
                )

        # /search ─────────────────────────────────────────────────────────
        elif cmd == "/search":
            if len(parts) < 2:
                await reply(bot, chat_id,
                    "Usage: `/search QUERY`\n_Example: /search Infosys_"
                )
            else:
                query = " ".join(parts[1:])
                results = fetcher.search_all_exchanges(query)
                if not results:
                    await reply(bot, chat_id,
                        f"❌ No companies found matching *{query}*"
                    )
                else:
                    lines = []
                    for r in results:
                        tick = "✓ " if db.is_in_watchlist(r["symbol"], r["exchange"]) else ""
                        lines.append(
                            f"{tick}`{r['symbol']}` \\({r['exchange']}\\) – {r['name']}"
                        )
                    await reply(bot, chat_id,
                        f"🔍 *Results for '{query}':*\n\n"
                        + "\n".join(lines)
                        + "\n\n_To add: /add SYMBOL EXCHANGE_\n"
                          "_e\\.g\\. /add INFY NSE_"
                    )

        # /latestAnn ──────────────────────────────────────────────────────
        elif cmd == "/latestann":
            if len(parts) < 2:
                await reply(
                    bot,
                    chat_id,
                    "Usage: `/latestAnn SYMBOL [EXCHANGE]`\n"
                    "_Exchange defaults to NSE if omitted._\n"
                    "_Example: /latestAnn INFY NSE_",
                )
            else:
                symbol = parts[1].upper()
                exchange = parts[2].upper() if len(parts) >= 3 else "NSE"

                if exchange not in ("NSE", "BSE"):
                    await reply(bot, chat_id, "❌ Exchange must be `NSE` or `BSE`.")
                else:
                    anns = fetcher.get_announcements(symbol, exchange)[:5]
                    if not anns:
                        await reply(
                            bot,
                            chat_id,
                            f"No recent announcements found for *{symbol}* ({exchange}).",
                        )
                    else:
                        await reply(
                            bot,
                            chat_id,
                            f"📌 Latest 5 announcements for {symbol} ({exchange})\n"
                            f"(This does not change your watchlist)",
                            parse_mode=None,
                        )
                        for i, ann in enumerate(anns, 1):
                            resolved = fetcher.resolve_statement_link(
                                symbol,
                                exchange,
                                ann.get("link", ""),
                            )
                            src = resolved.get("source", exchange)
                            download_link = resolved.get("link", "")
                            release_link = ann.get("release_link") or exchange_fallback_link(symbol, exchange)
                            summary = ann.get("description") or ann.get("title", "N/A")
                            message = (
                                f"[{i}/5] Announcement for {symbol} ({exchange})\n\n"
                                f"Type of Information: {ann.get('type', 'Announcement')}\n"
                                f"Information Date: {ann.get('date', 'N/A')}\n"
                                f"Summary: {summary}\n"
                                f"Published Date: {ann.get('published_date', ann.get('date', 'N/A'))}\n"
                                f"Release Link: {release_link}\n"
                                f"Download Copy: {(f'({src}) ' + download_link) if download_link else 'Not available'}"
                            )
                            await reply(bot, chat_id, message, parse_mode=None)

        # /latestAct ──────────────────────────────────────────────────────
        elif cmd == "/latestact":
            if len(parts) < 2:
                await reply(
                    bot,
                    chat_id,
                    "Usage: `/latestAct SYMBOL [EXCHANGE]`\n"
                    "_Exchange defaults to NSE if omitted._\n"
                    "_Example: /latestAct INFY NSE_",
                )
            else:
                symbol = parts[1].upper()
                exchange = parts[2].upper() if len(parts) >= 3 else "NSE"

                if exchange not in ("NSE", "BSE"):
                    await reply(bot, chat_id, "❌ Exchange must be `NSE` or `BSE`.")
                else:
                    actions = fetcher.get_corporate_actions(symbol, exchange)
                    ten_years_ago = datetime.now().timestamp() - (10 * 365.25 * 24 * 3600)

                    filtered = []
                    for act in actions:
                        dt = parse_flexible_date(act.get("date", ""))
                        if dt is None or dt.timestamp() >= ten_years_ago:
                            filtered.append(act)

                    if not filtered:
                        await reply(
                            bot,
                            chat_id,
                            f"No corporate actions found for last 10 years for *{symbol}* ({exchange}).",
                        )
                    else:
                        price_lines = []
                        meeting_lines = []
                        for idx, act in enumerate(filtered, 1):
                            line = f"{idx}. {act.get('date', 'N/A')} - {act.get('title', 'N/A')}"
                            if classify_action_group(act) == "meeting":
                                meeting_lines.append(line)
                            else:
                                price_lines.append(line)

                        await send_chunked_lines(
                            bot,
                            chat_id,
                            (
                                f"📈 Price/Capital related actions (last 10 years) for {symbol} ({exchange})\n"
                                f"Count: {len(price_lines)}"
                            ),
                            price_lines,
                        )
                        await send_chunked_lines(
                            bot,
                            chat_id,
                            (
                                f"🗓️ Meetings/Discussions (last 10 years) for {symbol} ({exchange})\n"
                                f"Count: {len(meeting_lines)}"
                            ),
                            meeting_lines,
                        )

        # /add ────────────────────────────────────────────────────────────
        elif cmd == "/add":
            if len(parts) < 2:
                await reply(bot, chat_id,
                    "Usage: `/add SYMBOL \\[EXCHANGE\\]`\n"
                    "_Exchange defaults to NSE if omitted\\._\n"
                    "_Example: /add INFY NSE_"
                )
            else:
                symbol   = parts[1].upper()
                exchange = parts[2].upper() if len(parts) >= 3 else "NSE"

                if exchange not in ("NSE", "BSE"):
                    await reply(bot, chat_id,
                        f"❌ Unknown exchange *{exchange}*\\. Use `NSE` or `BSE`\\."
                    )
                else:
                    company_name = fetcher.get_company_name(symbol, exchange) or symbol
                    added = db.add_to_watchlist(symbol, company_name, exchange)
                    if added:
                        await reply(bot, chat_id,
                            f"✅ Added *{symbol}* \\({exchange}\\) – {company_name} to watchlist\\!"
                        )
                    else:
                        await reply(bot, chat_id,
                            f"⚠️ *{symbol}* \\({exchange}\\) is already in your watchlist\\."
                        )

        # /remove ─────────────────────────────────────────────────────────
        elif cmd == "/remove":
            if len(parts) < 2:
                watchlist = db.get_watchlist()
                if not watchlist:
                    await reply(bot, chat_id, "Your watchlist is empty\\.")
                else:
                    lines = "\n".join(
                        f"{i}\\. {c['symbol']} \\({c['exchange']}\\) – {c['name']}"
                        for i, c in enumerate(watchlist, 1)
                    )
                    await reply(bot, chat_id,
                        f"To remove, use:\n`/remove SYMBOL EXCHANGE`\n\n"
                        f"*Current watchlist:*\n{lines}\n\n"
                        f"_Example: /remove INFY NSE_"
                    )
            else:
                symbol   = parts[1].upper()
                exchange = parts[2].upper() if len(parts) >= 3 else "NSE"
                removed  = db.remove_from_watchlist(symbol, exchange)
                if removed:
                    await reply(bot, chat_id,
                        f"✅ Removed *{symbol}* \\({exchange}\\) from watchlist\\."
                    )
                else:
                    await reply(bot, chat_id,
                        f"❌ *{symbol}* \\({exchange}\\) was not found in your watchlist\\."
                    )

        # /status ─────────────────────────────────────────────────────────
        elif cmd == "/status":
            watchlist = db.get_watchlist()
            await reply(bot, chat_id,
                f"📊 *Bot Status*\n\n"
                f"📋 Watchlist: {len(watchlist)} companies\n"
                f"🔄 Poll interval: every 5 minutes\n"
                f"✅ Running via GitHub Actions"
            )

        # unknown ─────────────────────────────────────────────────────────
        else:
            await reply(bot, chat_id,
                f"❓ Unknown command `{cmd}`\\.\nSend `/help` for the list of commands\\."
            )

    db.set_last_update_id(last_id)
    logger.info(f"Updated last_update_id to {last_id}")


# ---------------------------------------------------------------------------
# Announcement checker
# ---------------------------------------------------------------------------

async def run_announcement_check(bot: Bot, db: Database, fetcher: StockFetcher):
    """Check NSE/BSE for each watchlisted company and send alerts."""
    watchlist = db.get_watchlist()
    logger.info(f"Checking {len(watchlist)} companies...")

    ann_count = 0
    act_count = 0

    for company in watchlist:
        symbol   = company["symbol"]
        exchange = company["exchange"]
        logger.info(f"  → {symbol} ({exchange})")

        try:
            for ann in fetcher.get_announcements(symbol, exchange)[:4]:
                if db.mark_announcement_processed(
                    symbol, exchange,
                    ann.get("id", ""), ann.get("title", ""), ann.get("date", ""),
                ):
                    ann_count += 1
                    resolved = fetcher.resolve_statement_link(
                        symbol,
                        exchange,
                        ann.get("link", ""),
                    )
                    src = resolved.get("source", exchange)
                    download_link = resolved.get("link", "")
                    release_link = ann.get("release_link") or exchange_fallback_link(symbol, exchange)
                    summary = ann.get("description") or ann.get("title", "N/A")
                    await send_to_all_chats(bot,
                        f"📢 New Announcement for {company['name']} ({symbol})\n"
                        f"Exchange: {exchange}\n\n"
                        f"Type of Information: {ann.get('type', 'Announcement')}\n"
                        f"Information Date: {ann.get('date', 'N/A')}\n"
                        f"Summary: {summary}\n"
                        f"Published Date: {ann.get('published_date', ann.get('date', 'N/A'))}\n"
                        f"Release Link: {release_link}\n"
                        f"Download Copy: {(f'({src}) ' + download_link) if download_link else 'Not available'}"
                    , parse_mode=None)
        except Exception as e:
            logger.error(f"Announcements error for {symbol}: {e}")

        try:
            for action in fetcher.get_corporate_actions(symbol, exchange)[:4]:
                if db.mark_corporate_action_processed(
                    symbol, exchange,
                    action.get("id", ""), action.get("type", ""),
                    action.get("title", ""), action.get("date", ""),
                ):
                    act_count += 1
                    resolved = fetcher.resolve_statement_link(
                        symbol,
                        exchange,
                        action.get("link", ""),
                    )
                    src = resolved.get("source", exchange)
                    link = resolved.get("link", "")
                    group_name = "Meetings/Discussions" if classify_action_group(action) == "meeting" else "Price/Capital Related"
                    await send_to_all_chats(bot,
                        f"💼 New Corporate Action for {company['name']} ({symbol})\n"
                        f"Exchange: {exchange}\n\n"
                        f"Category Group: {group_name}\n"
                        f"Date: {action.get('date', 'N/A')}\n"
                        f"Summary: {action.get('title', 'N/A')}\n"
                        f"Type: {action.get('type', 'N/A')}\n"
                        f"Download Copy: {(f'({src}) ' + link) if link else 'Not available'}"
                    , parse_mode=None)
        except Exception as e:
            logger.error(f"Corporate actions error for {symbol}: {e}")

    return ann_count, act_count, len(watchlist)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    db      = Database()
    fetcher = StockFetcher()
    bot     = Bot(token=TELEGRAM_BOT_TOKEN)

    # Verify bot token
    try:
        bot_info = await bot.get_me()
        logger.info(f"✓ Bot connected: @{bot_info.username}")
    except Exception as e:
        logger.error(f"✗ Bot connection failed: {e}")
        return

    logger.info(f"✓ Chat IDs: {TELEGRAM_CHAT_IDS}")

    # 1. Process any pending commands
    await process_commands(bot, db, fetcher)

    # 2. Check for new announcements
    ann_count, act_count, total = await run_announcement_check(bot, db, fetcher)

    # 3. Send daily summary once per day (only if new day)
    today = datetime.now().strftime("%Y-%m-%d")
    last_summary_date = db.get_last_daily_summary_date()
    if last_summary_date != today:
        # Current monitored symbols for clarity
        monitored = db.get_watchlist()
        monitored_list = ", ".join(
            [f"{x['symbol']}({x['exchange']})" for x in monitored]
        ) or "None"
        await send_to_all_chats(bot,
            f"📋 *Daily Watchlist Summary*\n\n"
            f"Monitored Companies ({total}): {monitored_list}\n\n"
            f"_Bot polling every 5 minutes. New alerts will appear here._ "
        )
        db.set_last_daily_summary_date(today)


if __name__ == "__main__":
    asyncio.run(main())

