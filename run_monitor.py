"""Standalone polling + command-handling script for GitHub Actions.

Runs every 5 minutes via GitHub Actions cron.
Each run:
  1. Processes any Telegram commands sent since last run.
  2. Checks sources for new bulletins/activities for registered entities.
  3. Sends alerts to all configured chat IDs.

Commands (send these to your bot on Telegram):
  /start or /help          – show command list
  /add TAG [SOURCE]        – e.g. /add NOCIL SRCA  (default source: SRCA)
  /remove TAG [SOURCE]     – e.g. /remove NOCIL SRCA
  /list                    – show current registry
  /search QUERY            – search across all sources
    /latestBul TAG [SOURCE] – latest 5 bulletins (5 separate messages)
    /latestEvt TAG [SOURCE] – activity summary for last 10 years
  /status                  – bot status
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from database import Database
from data_fetcher import SRCB_CODES, DataFetcher, SRCA_HOST, SRCB_HOST
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS
from telegram import Bot
from itertools import islice

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


def source_fallback_link(symbol: str, source: str) -> str:
    """Return a stable fallback page URL for the tag/source."""
    if source.upper() == "SRCA":
        return f"https://www.{SRCA_HOST}/get-quotes/equity?symbol={symbol.upper()}"
    scrip = SRCB_CODES.get(symbol.upper(), "")
    if scrip:
        path = "sto" "ck-share-price"
        return f"https://www.{SRCB_HOST}/{path}/-/-/{scrip}/"
    return f"https://www.{SRCB_HOST}/"


def parse_flexible_date(date_str: str) -> Optional[datetime]:
    """Best-effort parser for source date formats."""
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


def classify_event_type(action: dict) -> str:
    """Group activities into session/discussion vs price/capital related buckets."""
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

async def process_commands(bot: Bot, db: Database, fetcher: DataFetcher):
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
                "🤖 *Pulse Monitor Bot*\n\n"
                "*Commands:*\n"
                "`/add TAG [SOURCE]` – add to registry\n"
                "  _e.g. /add NOCIL SRCA  or  /add APARAJYA SRCB_\n\n"
                "`/remove TAG [SOURCE]` – remove from registry\n"
                "  _e.g. /remove NOCIL SRCA_\n\n"
                "`/list` – show your registry\n"
                "`/view` – alias for /list\n"
                "`/search QUERY` – find an entity\n"
                "`/latestBul TAG [SOURCE]` – latest 5 bulletins\n"
                "`/latestEvt TAG [SOURCE]` – 10-year activity summary\n"
                "`/check` – run immediate check\n"
                "`/status` – bot status\n"
                "`/help` – show this message\n\n"
                "_Commands are processed within 5 minutes \\(next scheduled run\\)._"
            )

        # /list (/view, /veiw aliases) ───────────────────────────────────
        elif cmd in ("/list", "/view", "/veiw"):
            registry_items = db.get_registry(chat_id)
            if not registry_items:
                await reply(bot, chat_id,
                    "📋 Your registry is empty\.\n"
                    "Use `/add TAG SOURCE` to add an entity\.\n"
                    "_Example: /add NOCIL SRCA_"
                )
            else:
                lines = "\n".join(
                    f"{i}\\. {c['symbol']} \\({c['source']}\\) – {c['name']}"
                    for i, c in enumerate(registry_items, 1)
                )
                await reply(bot, chat_id,
                    f"📋 *Your Registry \\({len(registry_items)} entities\\):*\n\n{lines}"
                )

        # /search ─────────────────────────────────────────────────────────
        elif cmd == "/search":
            if len(parts) < 2:
                await reply(bot, chat_id,
                    "Usage: `/search QUERY`\n_Example: /search NOCIL_"
                )
            else:
                query = " ".join(parts[1:])
                results = fetcher.search_all_sources(query)
                if not results:
                    await reply(bot, chat_id,
                        f"❌ No entities found matching *{query}*"
                    )
                else:
                    lines = []
                    for r in results:
                        tick = "✓ " if db.is_in_registry(chat_id, r["symbol"], r["source"]) else ""
                        lines.append(
                            f"{tick}`{r['symbol']}` \\({r['source']}\\) – {r['name']}"
                        )
                    await reply(bot, chat_id,
                        f"🔍 *Results for '{query}':*\n\n"
                        + "\n".join(lines)
                        + "\n\n_To add: /add TAG SOURCE_\n"
                          "_e\.g\. /add NOCIL SRCA_"
                    )

        # /latestBul ──────────────────────────────────────────────────────
        elif cmd == "/latestbul":
            if len(parts) < 2:
                await reply(
                    bot,
                    chat_id,
                    "Usage: `/latestBul TAG [SOURCE]`\n"
                    "_Source defaults to SRCA if omitted._\n"
                    "_Example: /latestBul NOCIL SRCA_",
                )
            else:
                symbol = parts[1].upper()
                source = parts[2].upper() if len(parts) >= 3 else "SRCA"

                if source not in ("SRCA", "SRCB"):
                    await reply(bot, chat_id, "❌ Source must be `SRCA` or `SRCB`.")
                else:
                    anns = fetcher.get_bulletins(symbol, source)[:5]
                    if not anns:
                        await reply(
                            bot,
                            chat_id,
                            f"No recent bulletins found for *{symbol}* ({source}).",
                        )
                    else:
                        await reply(
                            bot,
                            chat_id,
                            f"📌 Latest 5 bulletins for {symbol} ({source})\n"
                            f"(This does not change your registry)",
                            parse_mode=None,
                        )
                        for i, ann in enumerate(anns, 1):
                            resolved = fetcher.resolve_doc_link(
                                symbol,
                                source,
                                ann.get("link", ""),
                            )
                            src = resolved.get("source", source)
                            download_link = resolved.get("link", "")
                            release_link = ann.get("release_link") or source_fallback_link(symbol, source)
                            summary = ann.get("description") or ann.get("title", "N/A")
                            message = (
                                f"[{i}/5] Bulletin for {symbol} ({source})\n\n"
                                f"Type: {ann.get('type', 'Bulletin')}\n"
                                f"Date: {ann.get('date', 'N/A')}\n"
                                f"Summary: {summary}\n"
                                f"Published: {ann.get('published_date', ann.get('date', 'N/A'))}\n"
                                f"Release Link: {release_link}\n"
                                f"Download Copy: {(f'({src}) ' + download_link) if download_link else 'Not available'}"
                            )
                            await reply(bot, chat_id, message, parse_mode=None)

        # /latestEvt ──────────────────────────────────────────────────────
        elif cmd == "/latestevt":
            if len(parts) < 2:
                await reply(
                    bot,
                    chat_id,
                    "Usage: `/latestEvt TAG [SOURCE]`\n"
                    "_Source defaults to SRCA if omitted._\n"
                    "_Example: /latestEvt NOCIL SRCA_",
                )
            else:
                symbol = parts[1].upper()
                source = parts[2].upper() if len(parts) >= 3 else "SRCA"

                if source not in ("SRCA", "SRCB"):
                    await reply(bot, chat_id, "❌ Source must be `SRCA` or `SRCB`.")
                else:
                    actions = fetcher.get_activities(symbol, source)
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
                            f"No activities found for last 10 years for *{symbol}* ({source}).",
                        )
                    else:
                        price_lines = []
                        meeting_lines = []
                        for idx, act in enumerate(filtered, 1):
                            line = f"{idx}. {act.get('date', 'N/A')} - {act.get('title', 'N/A')}"
                            if classify_event_type(act) == "meeting":
                                meeting_lines.append(line)
                            else:
                                price_lines.append(line)

                        await send_chunked_lines(
                            bot,
                            chat_id,
                            (
                                f"📈 Price/Capital related activities (last 10 years) for {symbol} ({source})\n"
                                f"Count: {len(price_lines)}"
                            ),
                            price_lines,
                        )
                        await send_chunked_lines(
                            bot,
                            chat_id,
                            (
                                f"🗓️ Sessions/Discussions (last 10 years) for {symbol} ({source})\n"
                                f"Count: {len(meeting_lines)}"
                            ),
                            meeting_lines,
                        )

        # /add ────────────────────────────────────────────────────────────
        elif cmd == "/add":
            if len(parts) < 2:
                await reply(bot, chat_id,
                    "Usage: `/add TAG \\[SOURCE\\]`\n"
                    "_Source defaults to SRCA if omitted\\._\n"
                    "_Example: /add NOCIL SRCA_"
                )
            else:
                symbol   = parts[1].upper()
                source = parts[2].upper() if len(parts) >= 3 else "SRCA"

                if source not in ("SRCA", "SRCB"):
                    await reply(bot, chat_id,
                        f"❌ Unknown source *{source}*\\. Use `SRCA` or `SRCB`\\."
                    )
                else:
                    entity_name = fetcher.get_entity_name(symbol, source) or symbol
                    added = db.add_to_registry(chat_id, symbol, entity_name, source)
                    if added:
                        await reply(bot, chat_id,
                            f"✅ Added *{symbol}* \\({source}\\) – {entity_name} to registry\\!"
                        )
                    else:
                        await reply(bot, chat_id,
                            f"⚠️ *{symbol}* \\({source}\\) is already in your registry\\."
                        )

        # /remove ─────────────────────────────────────────────────────────
        elif cmd == "/remove":
            if len(parts) < 2:
                registry_items = db.get_registry(chat_id)
                if not registry_items:
                    await reply(bot, chat_id, "Your registry is empty\\.")
                else:
                    lines = "\n".join(
                        f"{i}\\. {c['symbol']} \\({c['source']}\\) – {c['name']}"
                        for i, c in enumerate(registry_items, 1)
                    )
                    await reply(bot, chat_id,
                        f"To remove, use:\n`/remove TAG SOURCE`\n\n"
                        f"*Current registry:*\n{lines}\n\n"
                        f"_Example: /remove NOCIL SRCA_"
                    )
            else:
                symbol   = parts[1].upper()
                source = parts[2].upper() if len(parts) >= 3 else "SRCA"
                removed  = db.remove_from_registry(chat_id, symbol, source)
                if removed:
                    await reply(bot, chat_id,
                        f"✅ Removed *{symbol}* \\({source}\\) from registry\\."
                    )
                else:
                    await reply(bot, chat_id,
                        f"❌ *{symbol}* \\({source}\\) was not found in your registry\\."
                    )

        # /status ─────────────────────────────────────────────────────────
        elif cmd == "/status":
            registry_items = db.get_registry(chat_id)
            cache_size = len(fetcher._entity_name_cache)
            await reply(bot, chat_id,
                f"📊 *Bot Status*\n\n"
                f"📋 Your Registry: {len(registry_items)} entities\n"
                f"💾 Cached Names: {cache_size} entities\n"
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
# Update checker
# ---------------------------------------------------------------------------

async def process_entity_updates(
    bot: Bot,
    db: Database,
    fetcher: DataFetcher,
    chat_id: int,
    entity: dict,
) -> tuple[int, int]:
    """Process bulletins and activities for a single entity. Returns (new_bulletins, new_activities)."""
    symbol = entity["symbol"]
    source = entity["source"]
    ann_count = 0
    act_count = 0

    # Rotate user agent to avoid NSE detection
    fetcher._update_headers()

    logger.info(f"  → {symbol} ({source})")

    try:
        bulletins = fetcher.get_bulletins(symbol, source)[:4]
        for ann in bulletins:
            if db.mark_bulletin_processed(
                symbol, source,
                ann.get("id", ""), ann.get("title", ""), ann.get("date", ""),
            ):
                ann_count += 1
                try:
                    resolved = fetcher.resolve_doc_link(
                        symbol,
                        source,
                        ann.get("link", ""),
                    )
                    src = resolved.get("source", source)
                    download_link = resolved.get("link", "")
                    release_link = ann.get("release_link") or source_fallback_link(symbol, source)
                    summary = ann.get("description") or ann.get("title", "N/A")
                    await reply(bot, chat_id,
                        f"📢 New Bulletin for {entity['name']} ({symbol})\n"
                        f"Source: {source}\n\n"
                        f"Type: {ann.get('type', 'Bulletin')}\n"
                        f"Date: {ann.get('date', 'N/A')}\n"
                        f"Summary: {summary}\n"
                        f"Published: {ann.get('published_date', ann.get('date', 'N/A'))}\n"
                        f"Release Link: {release_link}\n"
                        f"Download Copy: {(f'({src}) ' + download_link) if download_link else 'Not available'}"
                    , parse_mode=None)
                except Exception as e:
                    logger.error(f"Failed to send bulletin alert for {symbol}: {e}")
    except Exception as e:
        logger.warning(f"Skipping bulletins for {symbol} ({source}): {e}")

    try:
        activities = fetcher.get_activities(symbol, source)[:4]
        for action in activities:
            if db.mark_activity_processed(
                symbol, source,
                action.get("id", ""), action.get("type", ""),
                action.get("title", ""), action.get("date", ""),
            ):
                act_count += 1
                try:
                    resolved = fetcher.resolve_doc_link(
                        symbol,
                        source,
                        action.get("link", ""),
                    )
                    src = resolved.get("source", source)
                    link = resolved.get("link", "")
                    group_name = "Sessions/Discussions" if classify_event_type(action) == "meeting" else "Price/Capital Related"
                    await reply(bot, chat_id,
                        f"💼 New Activity for {entity['name']} ({symbol})\n"
                        f"Source: {source}\n\n"
                        f"Category: {group_name}\n"
                        f"Date: {action.get('date', 'N/A')}\n"
                        f"Summary: {action.get('title', 'N/A')}\n"
                        f"Type: {action.get('type', 'N/A')}\n"
                        f"Download Copy: {(f'({src}) ' + link) if link else 'Not available'}"
                    , parse_mode=None)
                except Exception as e:
                    logger.error(f"Failed to send activity alert for {symbol}: {e}")
    except Exception as e:
        logger.warning(f"Skipping activities for {symbol} ({source}): {e}")

    return ann_count, act_count


async def run_update_check(bot: Bot, db: Database, fetcher: DataFetcher):
    """Check all sources for new bulletins/activities and send alerts per chat."""
    chat_ids = db.get_all_chat_ids()
    if not chat_ids:
        logger.info("No chats with registry entries found.")
        return 0, 0, 0

    total_ann_count = 0
    total_act_count = 0
    total_entities = 0

    for chat_id in chat_ids:
        registry_items = db.get_registry(chat_id)
        logger.info(f"Checking {len(registry_items)} entities for chat_id {chat_id}...")
        total_entities += len(registry_items)

        # Process up to 2 entities concurrently with 3s delay between each to avoid NSE rate-limiting
        semaphore = asyncio.Semaphore(2)

        async def process_with_semaphore(entity, delay: float):
            async with semaphore:
                # Spread out requests to NSE (3-5s delay between starts)
                await asyncio.sleep(delay)
                return await process_entity_updates(bot, db, fetcher, chat_id, entity)

        # Create tasks with staggered delays: 0s, 3s, 6s, 9s, ...
        tasks = [
            process_with_semaphore(entity, delay=i * 3.0)
            for i, entity in enumerate(registry_items)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Entity processing failed: {result}")
            else:
                ann_count, act_count = result
                total_ann_count += ann_count
                total_act_count += act_count

    return total_ann_count, total_act_count, total_entities


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    db      = Database()
    fetcher = DataFetcher()
    bot     = Bot(token=TELEGRAM_BOT_TOKEN)

    # Verify bot token
    try:
        bot_info = await bot.get_me()
        logger.info(f"✓ Bot connected: @{bot_info.username}")
    except Exception as e:
        logger.error(f"✗ Bot connection failed: {e}")
        return

    logger.info(f"✓ Chat IDs: {TELEGRAM_CHAT_IDS}")

    # Cleanup: Remove records older than 30 days (prevents DB bloat)
    db.clear_old_processed_records(days=30)

    # Clear cookies before fetching to avoid NSE rate limiting
    fetcher.clear_cookies()

    # 1. Process any pending commands
    await process_commands(bot, db, fetcher)

    # 2. Check for new updates
    ann_count, act_count, total = await run_update_check(bot, db, fetcher)

    # 3. Send daily summary once per day (only if new day)
    today = datetime.now().strftime("%Y-%m-%d")
    last_summary_date = db.get_last_daily_summary_date()
    if last_summary_date != today:
        # Send per-chat daily summary
        chat_ids = db.get_all_chat_ids()
        for chat_id in chat_ids:
            monitored = db.get_registry(chat_id)
            monitored_list = ", ".join(
                [f"{x['symbol']}({x['source']})" for x in monitored]
            ) or "None"
            await reply(bot, chat_id,
                f"📋 *Daily Registry Summary*\n\n"
                f"Your Tracked Entities ({len(monitored)}): {monitored_list}\n\n"
                f"_Bot polling every 5 minutes. New alerts will appear here._ "
            )
        db.set_last_daily_summary_date(today)


if __name__ == "__main__":
    asyncio.run(main())

