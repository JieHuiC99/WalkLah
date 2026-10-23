"""One small database interface for the report store: SQLite locally, Postgres when deployed.

Set DATABASE_URL (postgresql://user:password@host:port/db) to use Postgres. It is reached
with pg8000, a pure-Python driver (no compiled libraries). The SQL in app/report_store.py
is written to run on both: "?" placeholders, RETURNING for new ids and ON CONFLICT upserts.
"""

import os
import re
import sqlite3
import ssl
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator, List, Optional, Sequence
from urllib.parse import unquote, urlparse


class Row(dict):
    """A result row readable by column name or by position (like sqlite3.Row)."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class Result:
    def __init__(self, rows: List[Row], rowcount: int):
        self.rows, self.rowcount = rows, rowcount

    def fetchone(self) -> Optional[Row]:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> List[Row]:
        return self.rows

    def __iter__(self) -> Iterator[Row]:
        return iter(self.rows)


class Database:
    dialect = "sqlite"

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Result:
        raise NotImplementedError

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self) -> None:
        raise NotImplementedError

    def columns(self, table: str) -> List[str]:
        raise NotImplementedError


class SQLiteDatabase(Database):
    dialect = "sqlite"

    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Result:
        cur = self._conn.execute(sql, tuple(params))
        rows = [Row(zip(r.keys(), tuple(r))) for r in cur.fetchall()] if cur.description else []
        return Result(rows, cur.rowcount)

    def commit(self) -> None:
        self._conn.commit()

    def columns(self, table: str) -> List[str]:
        return [r["name"] for r in self.execute(f"PRAGMA table_info({table})")]


class PostgresDatabase(Database):
    dialect = "postgres"

    def __init__(self, url: str):
        self.url = url
        self._conn = None
        self._lock = threading.RLock()  # one connection, shared by the report store and search

    def _connect(self):
        import pg8000.dbapi

        u = urlparse(self.url)
        port = u.port or 5432
        # Encrypted like libpq's sslmode=require (Supabase signs with its own CA).
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self._conn = pg8000.dbapi.connect(
            user=unquote(u.username or ""), password=unquote(u.password or ""), host=u.hostname,
            port=port, database=(u.path or "/postgres").lstrip("/") or "postgres",
            ssl_context=context, timeout=20)
        # Every statement commits on its own, so no server connection stays pinned while an instance idles.
        self._conn.autocommit = True

    @staticmethod
    def translate(sql: str) -> str:
        """SQLite column types to Postgres ones (REAL would be single precision there)."""
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        return re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql)

    @classmethod
    def render(cls, sql: str, params: Sequence[Any]) -> str:
        """The statement with each "?" replaced by its value, quoted by pg8000.

        Sent as one simple-protocol message: Supabase's transaction pooler (port 6543) may hand the
        separate steps of a prepared statement to different server connections, which then fails with
        "unnamed prepared statement does not exist".
        """
        from pg8000.native import literal

        parts = cls.translate(sql).split("?")
        if len(parts) != len(params) + 1:
            raise ValueError(f"{len(parts) - 1} placeholders for {len(params)} values")
        out = [parts[0]]
        for value, part in zip(params, parts[1:]):
            out += [literal(value), part]
        return "".join(out)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Result:
        import pg8000.dbapi

        statement = self.render(sql, tuple(params))
        with self._lock:
            for attempt in (1, 2):
                if self._conn is None:
                    self._connect()
                cur = self._conn.cursor()
                try:
                    cur.execute(statement)  # no separate parameters: pg8000 uses the simple protocol
                    rows = []
                    if cur.description:
                        names = [d[0] for d in cur.description]
                        rows = [Row(zip(names, r)) for r in cur.fetchall()]
                    return Result(rows, cur.rowcount)
                except pg8000.dbapi.InterfaceError:
                    # The pooler closed an idle connection: reconnect once.
                    self._conn = None
                    if attempt == 2:
                        raise
            raise RuntimeError("unreachable")

    def commit(self) -> None:
        """Nothing to do: with autocommit every statement is already saved."""

    def columns(self, table: str) -> List[str]:
        return [r["column_name"] for r in self.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,))]


_SHARED: dict = {}
_SHARED_LOCK = threading.Lock()


def connect(path: Optional[str] = None) -> Database:
    """Postgres if a postgres:// URL is given (or DATABASE_URL is set and no path is), else SQLite."""
    target = (path or os.environ.get("DATABASE_URL") or "").strip().strip('"').strip("'")
    if target.startswith(("postgres://", "postgresql://")):
        # One connection per server instance: the free Supabase pooler allows only a few.
        with _SHARED_LOCK:
            if target not in _SHARED:
                _SHARED[target] = PostgresDatabase(target)
            return _SHARED[target]
    from .report_store import DEFAULT_DB

    default = DEFAULT_DB
    if os.environ.get("VERCEL"):  # read-only bundle: only /tmp is writable (and is not kept between instances)
        default = Path(tempfile.gettempdir()) / "walklah.db"
    return SQLiteDatabase(path or os.environ.get("WALKLAH_DB", str(default)))
