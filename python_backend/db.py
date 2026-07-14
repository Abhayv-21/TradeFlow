"""
db.py — Dual-mode database backend for TradeFlow.
Uses PostgreSQL (psycopg2) when DATABASE_URL env var is set,
otherwise falls back to local SQLite.
"""

import os
import re
import sqlite3
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
USE_PG = bool(DATABASE_URL)

# ── PostgreSQL mode ───────────────────────────────────────────────────────────
if USE_PG:
    import psycopg2
    import psycopg2.extras

    def query(sql: str, params=None) -> list:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params or [])
                try:
                    rows = cur.fetchall()
                except psycopg2.ProgrammingError:
                    rows = []
            conn.commit()
            return [dict(r) for r in rows] if rows else []
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def query_one(sql: str, params=None):
        rows = query(sql, params)
        return rows[0] if rows else None

    @contextmanager
    def get_conn():
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _test_connection():
        try:
            result = query("SELECT version()")
            ver = list(result[0].values())[0] if result else 'unknown'
            print(f'[DB] PostgreSQL connected OK')
            print(f'[DB] {ver[:60]}')
        except Exception as e:
            print(f'[DB] PostgreSQL connection FAILED: {e}')

# ── SQLite mode ───────────────────────────────────────────────────────────────
else:
    DB_PATH = os.getenv('SQLITE_PATH', 'tradeflow.db')
    DB_PATH = os.path.join(os.path.dirname(__file__), DB_PATH)

    def _dict_row(cursor, row):
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

    def _adapt(sql: str) -> str:
        sql = sql.replace('%s', '?')
        sql = re.sub(r'\s+FOR\s+UPDATE\b', '', sql, flags=re.IGNORECASE)
        # Boolean TRUE/FALSE → SQLite integer 1/0
        sql = re.sub(r'\bTRUE\b',  '1', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bFALSE\b', '0', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bNOW\s*\(\s*\)', "datetime('now')", sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bCURRENT_DATE\b', "date('now')", sql, flags=re.IGNORECASE)
        sql = re.sub(
            r'::\s*(INT|INTEGER|BIGINT|SMALLINT|TEXT|VARCHAR(\s*\(\d+\))?|NUMERIC(\s*\(\d+\s*,\s*\d+\))?'
            r'|FLOAT|REAL|DOUBLE\s*PRECISION|BOOLEAN|DATE|TIMESTAMP(\s*WITH\s*TIME\s*ZONE)?|CHAR(\s*\(\d+\))?)',
            '', sql, flags=re.IGNORECASE
        )
        sql = re.sub(
            r"datetime\('now'\)\s*-\s*\(\s*\?\s*\|\|\s*'\s*days\s*'\s*\)",
            "datetime('now', '-' || ? || ' days')",
            sql, flags=re.IGNORECASE
        )
        sql = re.sub(
            r"datetime\('now'\)\s*-\s*INTERVAL\s*'(\d+)\s+(\w+)'",
            lambda m: f"datetime('now', '-{m.group(1)} {m.group(2)}')",
            sql, flags=re.IGNORECASE
        )
        return sql

    class _Cursor:
        def __init__(self, cur):
            self._cur = cur

        def execute(self, sql, params=None):
            self._cur.execute(_adapt(sql), params or [])
            return self

        def fetchone(self):
            return self._cur.fetchone()

        def fetchall(self):
            return self._cur.fetchall() or []

        def __iter__(self):
            return iter(self._cur)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    class _Conn:
        def __init__(self, path):
            self._c = sqlite3.connect(path)
            self._c.row_factory = _dict_row
            self._c.execute("PRAGMA journal_mode=WAL")
            self._c.execute("PRAGMA foreign_keys=ON")

        def cursor(self, cursor_factory=None):
            return _Cursor(self._c.cursor())

        def commit(self):   self._c.commit()
        def rollback(self): self._c.rollback()
        def close(self):    self._c.close()

        def execute(self, sql, params=()):
            return self._c.execute(_adapt(sql), params)

    def query(sql: str, params=None) -> list:
        conn = _Conn(DB_PATH)
        try:
            rows = conn._c.execute(_adapt(sql), params or []).fetchall()
            conn._c.commit()
            return rows or []
        except Exception:
            conn._c.rollback()
            raise
        finally:
            conn._c.close()

    def query_one(sql: str, params=None):
        rows = query(sql, params)
        return rows[0] if rows else None

    @contextmanager
    def get_conn():
        conn = _Conn(DB_PATH)
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _test_connection():
        try:
            result = query("SELECT sqlite_version() AS version")
            ver = result[0]['version'] if result else 'unknown'
            print(f'[DB] SQLite connected OK  version={ver}')
            print(f'[DB] File: {os.path.abspath(DB_PATH)}')
        except Exception as e:
            print(f'[DB] SQLite connection FAILED: {e}')


_test_connection()
