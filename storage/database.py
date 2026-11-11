"""SQLite database manager with WAL mode, atomic transactions, and schema migrations."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, List, Tuple


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


_V1_STATEMENTS: Tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL UNIQUE,
        name TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        bundle_dir TEXT,
        post_text TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
        group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        post_url TEXT,
        fb_post_id TEXT,
        details TEXT NOT NULL DEFAULT '',
        published_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(campaign_id, group_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS post_metrics_hourly (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        captured_at TEXT NOT NULL,
        day_of_week INTEGER NOT NULL,
        hour_of_day INTEGER NOT NULL,
        likes_count INTEGER NOT NULL DEFAULT 0,
        comments_count INTEGER NOT NULL DEFAULT 0,
        shares_count INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        fb_comment_id TEXT NOT NULL UNIQUE,
        author_name TEXT,
        content TEXT NOT NULL,
        comment_timestamp TEXT,
        captured_at TEXT NOT NULL,
        needs_reply INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reply_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comment_id INTEGER NOT NULL UNIQUE REFERENCES comments(id) ON DELETE CASCADE,
        provider TEXT NOT NULL,
        model_name TEXT NOT NULL,
        suggested_reply TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
        approved_at TEXT,
        sent_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_groups_status ON groups(status)",
    "CREATE INDEX IF NOT EXISTS idx_campaigns_active ON campaigns(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_posts_campaign_status ON posts(campaign_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_posts_url ON posts(post_url)",
    "CREATE INDEX IF NOT EXISTS idx_metrics_post_time ON post_metrics_hourly(post_id, captured_at)",
    "CREATE INDEX IF NOT EXISTS idx_comments_needs_reply ON comments(needs_reply)",
)


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Create initial relational schema for groups, campaigns, posts, metrics, and comments."""
    for statement in _V1_STATEMENTS:
        conn.execute(statement)


MIGRATIONS: List[Tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (1, _migrate_v1),
]


class DatabaseManager:
    """Manages embedded SQLite connections, WAL concurrency, and atomic transactions."""

    def __init__(self, db_path: Path | str) -> None:
        self.raw_path = str(db_path)
        self.is_memory = self.raw_path == ":memory:"
        self.db_path = Path(db_path) if not self.is_memory else None
        self._write_lock = threading.RLock()
        self._thread_local = threading.local()
        self._memory_conn: sqlite3.Connection | None = None
        self._open_connections: List[sqlite3.Connection] = []

        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.initialize()
        except Exception:
            self.close()
            raise

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.raw_path,
            timeout=30.0,
            isolation_level=None,  # Explicit BEGIN / COMMIT / ROLLBACK control
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        if not self.is_memory:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 15000;")
        return conn

    def get_connection(self) -> sqlite3.Connection:
        """Return a configured SQLite connection safe for the current thread."""
        if self.is_memory:
            if self._memory_conn is None:
                self._memory_conn = self._create_connection()
                self._open_connections.append(self._memory_conn)
            return self._memory_conn

        conn = getattr(self._thread_local, "conn", None)
        if conn is None:
            conn = self._create_connection()
            self._thread_local.conn = conn
            with self._write_lock:
                self._open_connections.append(conn)
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Execute database mutations atomically with COMMIT and ROLLBACK."""
        with self._write_lock:
            conn = self.get_connection()
            in_tx = conn.in_transaction
            if not in_tx:
                conn.execute("BEGIN IMMEDIATE;")
            try:
                yield conn
                if not in_tx:
                    conn.execute("COMMIT;")
            except Exception:
                if not in_tx and conn.in_transaction:
                    conn.execute("ROLLBACK;")
                raise

    @contextmanager
    def read_cursor(self) -> Iterator[sqlite3.Cursor]:
        """Yield a cursor for read-only queries without holding the write lock longer than needed."""
        if self.is_memory:
            with self._write_lock:
                cur = self.get_connection().cursor()
                try:
                    yield cur
                finally:
                    cur.close()
        else:
            cur = self.get_connection().cursor()
            try:
                yield cur
            finally:
                cur.close()

    def initialize(self) -> None:
        """Apply pending schema migrations idempotently."""
        with self.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                """
            )
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            for version, migration_fn in MIGRATIONS:
                if version not in applied:
                    migration_fn(conn)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                        (version, utc_now_iso()),
                    )

    def close(self) -> None:
        """Close all tracked SQLite connections."""
        with self._write_lock:
            for conn in self._open_connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._open_connections.clear()
            self._memory_conn = None
            if hasattr(self._thread_local, "conn"):
                delattr(self._thread_local, "conn")
