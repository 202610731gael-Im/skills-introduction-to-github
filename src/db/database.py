"""
SQLite 데이터베이스 관리 모듈
공고 정보를 저장·조회하고 중복 수집을 방지한다.
"""
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional

from ..crawler.base_crawler import Announcement


logger = logging.getLogger(__name__)


class Database:
    """SQLite 기반 공고 데이터베이스"""

    DDL = """
    CREATE TABLE IF NOT EXISTS announcements (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id         TEXT NOT NULL,
        site_name       TEXT NOT NULL,
        announcement_id TEXT NOT NULL,
        title           TEXT NOT NULL,
        url             TEXT NOT NULL,
        organization    TEXT,
        category        TEXT,
        target          TEXT,
        region          TEXT,
        support_amount  TEXT,
        start_date      TEXT,
        end_date        TEXT,
        description     TEXT,
        raw_content     TEXT,
        attachments     TEXT,           -- JSON array
        collected_at    TEXT NOT NULL,
        eligibility_score  REAL DEFAULT 0.0,
        eligibility_reason TEXT,
        UNIQUE (site_id, announcement_id)
    );

    CREATE INDEX IF NOT EXISTS idx_site_id ON announcements(site_id);
    CREATE INDEX IF NOT EXISTS idx_collected_at ON announcements(collected_at);
    CREATE INDEX IF NOT EXISTS idx_score ON announcements(eligibility_score);
    """

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(self.DDL)
        logger.info("데이터베이스 초기화 완료: %s", self.db_path)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def is_known(self, site_id: str, announcement_id: str) -> bool:
        """이미 수집된 공고인지 확인한다."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM announcements WHERE site_id=? AND announcement_id=?",
                (site_id, announcement_id),
            ).fetchone()
        return row is not None

    def save(self, ann: Announcement) -> bool:
        """
        공고를 저장한다.

        Returns:
            True if newly inserted, False if already exists (ignored)
        """
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO announcements
                        (site_id, site_name, announcement_id, title, url,
                         organization, category, target, region, support_amount,
                         start_date, end_date, description, raw_content,
                         attachments, collected_at,
                         eligibility_score, eligibility_reason)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ann.site_id, ann.site_name, ann.announcement_id,
                        ann.title, ann.url, ann.organization, ann.category,
                        ann.target, ann.region, ann.support_amount,
                        ann.start_date, ann.end_date, ann.description,
                        ann.raw_content, json.dumps(ann.attachments, ensure_ascii=False),
                        ann.collected_at, ann.eligibility_score, ann.eligibility_reason,
                    ),
                )
            return True
        except Exception as exc:
            logger.error("공고 저장 실패 (%s): %s", ann.announcement_id, exc)
            return False

    def update_score(self, site_id: str, announcement_id: str,
                     score: float, reason: str):
        """적합도 점수 업데이트"""
        with self._connect() as conn:
            conn.execute(
                """UPDATE announcements
                   SET eligibility_score=?, eligibility_reason=?
                   WHERE site_id=? AND announcement_id=?""",
                (score, reason, site_id, announcement_id),
            )

    def get_high_score_announcements(self, min_score: float = 70.0) -> List[Announcement]:
        """적합도 점수가 기준 이상인 공고 목록 반환"""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM announcements
                   WHERE eligibility_score >= ?
                   ORDER BY eligibility_score DESC, collected_at DESC""",
                (min_score,),
            ).fetchall()
        return [self._row_to_announcement(r) for r in rows]

    def get_today_announcements(self) -> List[Announcement]:
        """오늘 수집된 공고 목록 반환"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM announcements WHERE collected_at LIKE ? ORDER BY eligibility_score DESC",
                (f"{today}%",),
            ).fetchall()
        return [self._row_to_announcement(r) for r in rows]

    @staticmethod
    def _row_to_announcement(row: sqlite3.Row) -> Announcement:
        ann = Announcement(
            site_id=row["site_id"],
            site_name=row["site_name"],
            announcement_id=row["announcement_id"],
            title=row["title"],
            url=row["url"],
            organization=row["organization"] or "",
            category=row["category"] or "",
            target=row["target"] or "",
            region=row["region"] or "",
            support_amount=row["support_amount"] or "",
            start_date=row["start_date"],
            end_date=row["end_date"],
            description=row["description"] or "",
            raw_content=row["raw_content"] or "",
            attachments=json.loads(row["attachments"] or "[]"),
            collected_at=row["collected_at"],
            eligibility_score=row["eligibility_score"] or 0.0,
            eligibility_reason=row["eligibility_reason"] or "",
        )
        return ann
