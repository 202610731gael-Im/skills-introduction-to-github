"""
단위 테스트 - 데이터베이스
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.crawler.base_crawler import Announcement
from src.db.database import Database


def make_ann(ann_id: str, site_id: str = "test") -> Announcement:
    return Announcement(
        site_id=site_id,
        site_name="테스트사이트",
        announcement_id=ann_id,
        title=f"공고_{ann_id}",
        url=f"https://example.com/{ann_id}",
        organization="테스트기관",
        eligibility_score=75.0,
        eligibility_reason="테스트 근거",
    )


def test_save_and_is_known():
    """저장 후 is_known이 True를 반환해야 함"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = Database(db_path)
        ann = make_ann("001")
        assert not db.is_known("test", "001")
        db.save(ann)
        assert db.is_known("test", "001")
        print("[PASS] 저장/조회 테스트")
    finally:
        os.unlink(db_path)


def test_duplicate_save_ignored():
    """동일 공고를 두 번 저장해도 오류 없이 무시"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = Database(db_path)
        ann = make_ann("002")
        db.save(ann)
        db.save(ann)  # 중복 저장
        anns = db.get_high_score_announcements(70.0)
        assert len(anns) == 1
        print("[PASS] 중복 저장 무시 테스트")
    finally:
        os.unlink(db_path)


def test_get_high_score_announcements():
    """점수 필터가 올바르게 동작해야 함"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = Database(db_path)
        ann_high = make_ann("high")
        ann_high.eligibility_score = 85.0
        ann_low = make_ann("low")
        ann_low.eligibility_score = 50.0

        db.save(ann_high)
        db.save(ann_low)

        results = db.get_high_score_announcements(70.0)
        assert len(results) == 1
        assert results[0].announcement_id == "high"
        print("[PASS] 점수 필터 테스트")
    finally:
        os.unlink(db_path)


def test_update_score():
    """점수 업데이트가 올바르게 반영되어야 함"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = Database(db_path)
        ann = make_ann("update_test")
        ann.eligibility_score = 50.0
        db.save(ann)

        db.update_score("test", "update_test", 90.0, "업데이트된 근거")
        results = db.get_high_score_announcements(70.0)
        assert len(results) == 1
        assert results[0].eligibility_score == 90.0
        print("[PASS] 점수 업데이트 테스트")
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    test_save_and_is_known()
    test_duplicate_save_ignored()
    test_get_high_score_announcements()
    test_update_score()
    print("\n✅ 모든 DB 테스트 통과")
