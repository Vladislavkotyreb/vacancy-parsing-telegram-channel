from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
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
        conn.execute("PRAGMA journal_mode=WAL")
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

            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS subscribers (
                    user_id INTEGER PRIMARY KEY,
                    role TEXT NOT NULL,
                    subscribed_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS subscriber_sent (
                    user_id INTEGER NOT NULL,
                    vacancy_uid TEXT NOT NULL,
                    dedup_key TEXT,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, vacancy_uid)
                );

                CREATE INDEX IF NOT EXISTS idx_subscriber_sent_dedup
                    ON subscriber_sent (user_id, dedup_key);

                CREATE TABLE IF NOT EXISTS subscriber_roles (
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    PRIMARY KEY (user_id, role)
                );
                """
            )

            self._migrate_subscriber_roles(conn)

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

    def get_source_for_dedup(self, title: str, company: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT source FROM vacancies WHERE dedup_key = ? LIMIT 1",
                (dedupe_key(title, company or ""),),
            ).fetchone()
            return row["source"] if row else None

    def save_vacancy(self, vacancy: Vacancy) -> None:
        now = datetime.now(timezone.utc).isoformat()
        key = dedupe_key(vacancy.title, vacancy.company or "")
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM vacancies WHERE dedup_key = ? AND uid != ?",
                (key, vacancy.uid),
            )
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

    def _migrate_subscriber_roles(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT user_id, role FROM subscribers WHERE active = 1"
        ).fetchall()
        for row in rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO subscriber_roles (user_id, role)
                VALUES (?, ?)
                """,
                (int(row["user_id"]), row["role"]),
            )

    def set_subscriber(self, user_id: int, role: str) -> None:
        self.set_subscriber_roles(user_id, [role])

    def set_subscriber_roles(self, user_id: int, roles: list[str]) -> None:
        unique_roles = list(dict.fromkeys(roles))
        existing_roles = self.get_subscriber_roles(user_id)
        now = datetime.now(timezone.utc).isoformat()
        primary_role = unique_roles[0] if unique_roles else ""

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO subscribers (user_id, role, subscribed_at, active)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    role = excluded.role,
                    subscribed_at = CASE
                        WHEN subscribers.active = 0 THEN excluded.subscribed_at
                        ELSE subscribers.subscribed_at
                    END,
                    active = 1
                """,
                (user_id, primary_role, now),
            )
            conn.execute("DELETE FROM subscriber_roles WHERE user_id = ?", (user_id,))
            for role in unique_roles:
                conn.execute(
                    """
                    INSERT INTO subscriber_roles (user_id, role)
                    VALUES (?, ?)
                    """,
                    (user_id, role),
                )

        if set(existing_roles) != set(unique_roles):
            self.clear_subscriber_sent(user_id)

    def replace_category_roles(
        self, user_id: int, category_role_ids: set[str], roles: list[str]
    ) -> None:
        existing_roles = self.get_subscriber_roles(user_id)
        kept = [role for role in existing_roles if role not in category_role_ids]
        merged = list(dict.fromkeys(kept + roles))
        self.set_subscriber_roles(user_id, merged)

    def clear_subscriber_sent(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM subscriber_sent WHERE user_id = ?",
                (user_id,),
            )

    def get_subscriber_roles(self, user_id: int) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role
                FROM subscriber_roles
                WHERE user_id = ?
                ORDER BY role
                """,
                (user_id,),
            ).fetchall()
            if rows:
                return [row["role"] for row in rows]

            row = conn.execute(
                """
                SELECT role
                FROM subscribers
                WHERE user_id = ? AND active = 1
                """,
                (user_id,),
            ).fetchone()
            return [row["role"]] if row and row["role"] else []

    def get_subscriber(self, user_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, role, subscribed_at, active
                FROM subscribers
                WHERE user_id = ? AND active = 1
                """,
                (user_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["roles"] = self.get_subscriber_roles(user_id)
            return data

    def deactivate_subscriber(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE subscribers SET active = 0 WHERE user_id = ?",
                (user_id,),
            )

    def list_active_subscribers(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, role, subscribed_at
                FROM subscribers
                WHERE active = 1
                ORDER BY user_id
                """
            ).fetchall()
            result = []
            for row in rows:
                data = dict(row)
                data["roles"] = self.get_subscriber_roles(int(row["user_id"]))
                if not data["roles"] and data.get("role"):
                    data["roles"] = [data["role"]]
                result.append(data)
            return result

    def is_sent_to_subscriber(self, user_id: int, vacancy_uid: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM subscriber_sent
                WHERE user_id = ? AND vacancy_uid = ?
                LIMIT 1
                """,
                (user_id, vacancy_uid),
            ).fetchone()
            return row is not None

    def is_sent_to_subscriber_by_dedup(self, user_id: int, title: str, company: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM subscriber_sent
                WHERE user_id = ? AND dedup_key = ?
                LIMIT 1
                """,
                (user_id, dedupe_key(title, company or "")),
            ).fetchone()
            return row is not None

    def mark_sent_to_subscriber(self, user_id: int, vacancy: Vacancy) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO subscriber_sent
                (user_id, vacancy_uid, dedup_key, sent_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    vacancy.uid,
                    dedupe_key(vacancy.title, vacancy.company or ""),
                    now,
                ),
            )

    def _day_bounds_utc(self, timezone_name: str) -> tuple[str, str]:
        tz = ZoneInfo(timezone_name)
        today = datetime.now(tz).date()
        day_start = datetime.combine(today, time.min, tzinfo=tz).astimezone(timezone.utc)
        day_end = datetime.combine(today, time.max, tzinfo=tz).astimezone(timezone.utc)
        return day_start.isoformat(), day_end.isoformat()

    def count_active_subscribers(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM subscribers WHERE active = 1"
            ).fetchone()
            return int(row["cnt"])

    def subscriber_role_counts(self) -> list[tuple[str, int]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, COUNT(*) AS cnt
                FROM subscriber_roles
                GROUP BY role
                ORDER BY cnt DESC, role
                """
            ).fetchall()
            return [(row["role"], int(row["cnt"])) for row in rows]

    def subscriber_delivery_stats(
        self, timezone_name: str, days: Optional[int] = None
    ) -> dict[str, int]:
        day_start, day_end = self._day_bounds_utc(timezone_name)

        with self._connect() as conn:
            if days is None:
                period_row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS sent_total,
                        COUNT(DISTINCT user_id) AS users_reached
                    FROM subscriber_sent
                    """
                ).fetchone()
            else:
                tz = ZoneInfo(timezone_name)
                period_start = (
                    datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
                    - timedelta(days=days - 1)
                ).astimezone(timezone.utc)
                period_row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS sent_total,
                        COUNT(DISTINCT user_id) AS users_reached
                    FROM subscriber_sent
                    WHERE sent_at >= ?
                    """,
                    (period_start.isoformat(),),
                ).fetchone()
            today_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS sent_total,
                    COUNT(DISTINCT user_id) AS users_reached
                FROM subscriber_sent
                WHERE sent_at >= ? AND sent_at <= ?
                """,
                (day_start, day_end),
            ).fetchone()

        return {
            "sent_period": int(period_row["sent_total"]),
            "users_period": int(period_row["users_reached"]),
            "sent_today": int(today_row["sent_total"]),
            "users_today": int(today_row["users_reached"]),
        }

    def subscriber_sent_by_role(
        self, timezone_name: str, days: Optional[int] = None
    ) -> list[tuple[str, int]]:
        with self._connect() as conn:
            if days is None:
                rows = conn.execute(
                    """
                    SELECT sr.role AS role, COUNT(*) AS cnt
                    FROM subscriber_sent ss
                    JOIN subscriber_roles sr ON sr.user_id = ss.user_id
                    GROUP BY sr.role
                    ORDER BY cnt DESC, sr.role
                    """
                ).fetchall()
            else:
                tz = ZoneInfo(timezone_name)
                period_start = (
                    datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
                    - timedelta(days=days - 1)
                ).astimezone(timezone.utc)
                rows = conn.execute(
                    """
                    SELECT sr.role AS role, COUNT(*) AS cnt
                    FROM subscriber_sent ss
                    JOIN subscriber_roles sr ON sr.user_id = ss.user_id
                    WHERE ss.sent_at >= ?
                    GROUP BY sr.role
                    ORDER BY cnt DESC, sr.role
                    """,
                    (period_start.isoformat(),),
                ).fetchall()
            return [(row["role"], int(row["cnt"])) for row in rows]

    def channel_post_stats(
        self, timezone_name: str, days: Optional[int] = None
    ) -> dict[str, int | Optional[dict]]:
        day_start, day_end = self._day_bounds_utc(timezone_name)

        with self._connect() as conn:
            if days is None:
                posted_period = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM vacancies"
                ).fetchone()
            else:
                tz = ZoneInfo(timezone_name)
                period_start = (
                    datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
                    - timedelta(days=days - 1)
                ).astimezone(timezone.utc)
                posted_period = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM vacancies
                    WHERE first_seen_at >= ?
                    """,
                    (period_start.isoformat(),),
                ).fetchone()
            posted_today = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM vacancies
                WHERE first_seen_at >= ? AND first_seen_at <= ?
                """,
                (day_start, day_end),
            ).fetchone()
            last_run = conn.execute(
                """
                SELECT started_at, finished_at, found_total, posted_new, status
                FROM run_log
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        return {
            "total_known": self.total_known(),
            "posted_period": int(posted_period["cnt"]),
            "posted_today": int(posted_today["cnt"]),
            "last_run": dict(last_run) if last_run else None,
        }
