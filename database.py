"""Database setup and operations for Pulse Monitor."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from config import DB_PATH


class Database:
    """SQLite database handler for NSE Bot."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_db(self):
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Registry table - stores entities to monitor per chat_id
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    entity_name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, symbol, source)
                )
                """
            )

            # Processed bulletins - prevents duplicate alerts
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_bulletins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    bulletin_id TEXT NOT NULL,
                    bulletin_title TEXT,
                    bulletin_date TIMESTAMP,
                    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, source, bulletin_id)
                )
                """
            )

            # Processed activities - prevents duplicate alerts
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    activity_id TEXT NOT NULL,
                    activity_type TEXT,
                    activity_title TEXT,
                    activity_date TIMESTAMP,
                    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, source, activity_id)
                )
                """
            )

            # Bot state table – stores key/value pairs (e.g. last_update_id)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            # Daily summary tracking – stores last date daily summary was sent
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_summary (
                    id INTEGER PRIMARY KEY,
                    last_sent_date TEXT,
                    sent_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cursor.close()
            print(f"Database initialized at {self.db_path}")

    # ------------------------------------------------------------------
    # Bot state helpers (tracks last Telegram update_id)
    # ------------------------------------------------------------------

    def get_last_update_id(self) -> int:
        """Return the last processed Telegram update_id (0 if none)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM bot_state WHERE key = 'last_update_id'"
            )
            result = cursor.fetchone()
            cursor.close()
            return int(result[0]) if result else 0

    def set_last_update_id(self, update_id: int):
        """Persist the last processed Telegram update_id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO bot_state (key, value)
                VALUES ('last_update_id', ?)
                """,
                (str(update_id),),
            )
            cursor.close()

    def get_last_daily_summary_date(self) -> str:
        """Return the date (YYYY-MM-DD) of the last daily summary sent."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_sent_date FROM daily_summary WHERE id = 1")
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else None

    def set_last_daily_summary_date(self, date_str: str):
        """Persist the date when daily summary was last sent (YYYY-MM-DD format)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO daily_summary (id, last_sent_date, sent_timestamp)
                VALUES (1, ?, CURRENT_TIMESTAMP)
                """,
                (date_str,),
            )
            cursor.close()

    def add_to_registry(self, chat_id: int, symbol: str, entity_name: str, source: str = "SRCA") -> bool:
        """Add entity to registry for a specific chat."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO registry (chat_id, symbol, entity_name, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chat_id, symbol.upper(), entity_name, source.upper()),
                )
                cursor.close()
                return True
        except sqlite3.IntegrityError:
            return False

    def remove_from_registry(self, chat_id: int, symbol: str, source: str = "SRCA") -> bool:
        """Remove entity from registry for a specific chat."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM registry WHERE chat_id = ? AND symbol = ? AND source = ?",
                (chat_id, symbol.upper(), source.upper()),
            )
            cursor.close()
            return cursor.rowcount > 0

    def get_registry(self, chat_id: int) -> list:
        """Get all entities in registry for a specific chat."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol, entity_name, source FROM registry WHERE chat_id = ? ORDER BY entity_name", (chat_id,))
            results = cursor.fetchall()
            cursor.close()
            return [{"symbol": row[0], "name": row[1], "exchange": row[2]} for row in results]

    def is_in_registry(self, chat_id: int, symbol: str, source: str = "SRCA") -> bool:
        """Check if tag is in registry for a specific chat."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM registry WHERE chat_id = ? AND symbol = ? AND source = ?",
                (chat_id, symbol.upper(), source.upper()),
            )
            result = cursor.fetchone()
            cursor.close()
            return result is not None

    def mark_bulletin_processed(
        self, symbol: str, source: str, bulletin_id: str, title: str, date: str
    ) -> bool:
        """Mark bulletin as processed."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO processed_bulletins
                    (symbol, source, bulletin_id, bulletin_title, bulletin_date)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (symbol.upper(), source.upper(), bulletin_id, title, date),
                )
                cursor.close()
                return True
        except sqlite3.IntegrityError:
            return False

    def mark_activity_processed(
        self, symbol: str, source: str, activity_id: str, activity_type: str, title: str, date: str
    ) -> bool:
        """Mark activity as processed."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO processed_activities
                    (symbol, source, activity_id, activity_type, activity_title, activity_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (symbol.upper(), source.upper(), activity_id, activity_type, title, date),
                )
                cursor.close()
                return True
        except sqlite3.IntegrityError:
            return False

    def get_all_chat_ids(self) -> list:
        """Get all unique chat IDs that have registry entries."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT chat_id FROM registry")
            results = cursor.fetchall()
            cursor.close()
            return [row[0] for row in results]

    def clear_old_processed_records(self, days: int = 30):
        """Clear processed records older than specified days."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM processed_bulletins
                WHERE datetime(processed_date) < datetime('now', ? || ' days')
                """,
                (f"-{days}",),
            )
            cursor.execute(
                """
                DELETE FROM processed_activities
                WHERE datetime(processed_date) < datetime('now', ? || ' days')
                """,
                (f"-{days}",),
            )
            cursor.close()
