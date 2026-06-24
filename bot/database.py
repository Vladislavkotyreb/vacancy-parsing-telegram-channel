from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Iterator, Optional
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from bot.dates import dedupe_key
from bot.models import Vacancy


class VacancyDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._migrate()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS vacancies (
                    uid TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT,
                    salary TEXT,
                    location TEXT,
                    url TEXT NOT NULL,
                    published_at TEXT,
                    first_seen_at TEXT NOT NULL,
                    dedup_key TEXT
                );

                CREATE TABLE IF NOT EXISTS run_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    found_total INTEGER DEFAULT 0,
                    posted_new INTEGER DEFAULT 0,
                    status TEXT NOT NULL
                );
                """
            )

    def _migrate(self) -> None:
        with self._connect() as conn:
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(vacancies)")
            }
            if "dedup_key" not in columns:
                conn.execute("ALTER TABLE vacancies ADD COLUMN dedup_key TEXT")

            rows = conn.execute(
                "SELECT uid, title, company FROM vacancies WHERE dedup_key IS NULL"
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE vacancies SET dedup_key = ? WHERE uid = ?",
                    (dedupe_key(row["title"], row["company"] or ""), row["uid"]),
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vacancies_dedup_key ON vacancies (dedup_key)"
            )

    def is_known(self, uid: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM vacancies WHERE uid = ?", (uid,)
            ).fetchone()
            return row is not None

    def is_title_company_known(self, title: str, company: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM vacancies WHERE dedup_key = ? LIMIT 1",
                (dedupe_key(title, company or ""),),
            ).fetchone()
            return row is not None

    def save_vacancy(self, vacancy: Vacancy) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO vacancies
                (uid, source, external_id, title, company, salary, location, url, published_at, first_seen_at, dedup_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vacancy.uid,
                    vacancy.source,
                    vacancy.external_id,
                    vacancy.title,
                    vacancy.company,
                    vacancy.salary,
                    vacancy.location,
                    vacancy.url,
                    vacancy.published_at.isoformat() if vacancy.published_at else None,
                    now,
                    dedupe_key(vacancy.title, vacancy.company or ""),
                ),
            )

    def start_run(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO run_log (started_at, status) VALUES (?, ?)",
                (now, "running"),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, found_total: int, posted_new: int, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE run_log
                SET finished_at = ?, found_total = ?, posted_new = ?, status = ?
                WHERE id = ?
                """,
                (now, found_total, posted_new, status, run_id),
            )

    def last_run(self) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT started_at, finished_at, found_total, posted_new, status
                FROM run_log
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            return dict(row) if row else None

    def total_known(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM vacancies").fetchone()
            return int(row["cnt"])

    def has_successful_post_today(self, timezone_name: str) -> bool:
        tz = ZoneInfo(timezone_name)
        today = datetime.now(tz).date()
        day_start = datetime.combine(today, time.min, tzinfo=tz).astimezone(timezone.utc)
        day_end = datetime.combine(today, time.max, tzinfo=tz).astimezone(timezone.utc)

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM run_log
                WHERE status = 'ok'
                  AND started_at >= ?
                  AND started_at <= ?
                LIMIT 1
                """,
                (day_start.isoformat(), day_end.isoformat()),
            ).fetchone()
            return row is not None
