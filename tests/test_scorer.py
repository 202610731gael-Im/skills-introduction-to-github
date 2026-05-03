"""
단위 테스트 - 규칙 기반 적합성 분석기
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.crawler.base_crawler import Announcement
from src.scorer.eligibility_scorer import EligibilityScorer


COMPANY_PROFILE = {
    "name": "테스트 기업",
    "industry": "IT서비스",
    "sub_industry": "소프트웨어 개발",
    "established_year": 2020,
    "employee_count": 15,
    "annual_revenue_million": 500,
    "region": "서울",
    "certifications": ["벤처기업확인"],
    "company_type": "중소기업",
    "keywords": ["AI", "디지털전환", "R&D"],
}


def make_announcement(**kwargs) -> Announcement:
    defaults = dict(
        site_id="test",
        site_name="테스트사이트",
        announcement_id="test_001",
        title="테스트 공고",
        url="https://example.com",
    )
    defaults.update(kwargs)
    return Announcement(**defaults)


def test_high_score_matching_announcement():
    """키워드, 기업유형, 지역이 모두 일치하면 높은 점수"""
    scorer = EligibilityScorer(COMPANY_PROFILE, {"use_llm": False})
    ann = make_announcement(
        title="중소기업 AI 디지털전환 지원사업",
        target="중소기업, IT서비스 업종",
        category="R&D",
        raw_content="서울 소재 중소기업 대상으로 AI 및 디지털전환 R&D 자금을 지원합니다. 벤처기업확인 기업 우대.",
    )
    score, reason = scorer.score(ann)
    assert score >= 70, f"예상: >=70, 실제: {score}\n근거: {reason}"
    print(f"[PASS] 고점수 공고 테스트: {score:.1f}점")


def test_low_score_unrelated_announcement():
    """관련 없는 공고는 낮은 점수"""
    scorer = EligibilityScorer(COMPANY_PROFILE, {"use_llm": False})
    ann = make_announcement(
        title="농업 스마트팜 지원사업",
        target="농업법인, 농민",
        category="농업",
        raw_content="경상도 지역 농업법인을 대상으로 스마트팜 구축 비용을 지원합니다.",
    )
    score, reason = scorer.score(ann)
    assert score < 70, f"예상: <70, 실제: {score}\n근거: {reason}"
    print(f"[PASS] 저점수 공고 테스트: {score:.1f}점")


def test_national_region_gives_region_score():
    """'전국' 대상 공고는 지역 점수 획득"""
    scorer = EligibilityScorer(COMPANY_PROFILE, {"use_llm": False})
    ann = make_announcement(
        title="전국 중소기업 지원",
        target="전국 중소기업",
        raw_content="전국 모든 중소기업 대상",
    )
    score, reason = scorer.score(ann)
    assert "전국" in reason or score > 0
    print(f"[PASS] 전국 지역 테스트: {score:.1f}점")


def test_employee_count_limit():
    """직원 수 제한 조건 테스트"""
    scorer = EligibilityScorer(COMPANY_PROFILE, {"use_llm": False})

    # 30인 미만 조건 → 15명이므로 충족
    ann_ok = make_announcement(
        title="소기업 지원",
        raw_content="30인 미만 소기업을 대상으로 지원합니다.",
    )
    score_ok, _ = scorer.score(ann_ok)

    # 10인 미만 조건 → 15명이므로 미충족
    ann_fail = make_announcement(
        title="소기업 지원",
        raw_content="10인 미만 소기업을 대상으로 지원합니다.",
    )
    score_fail, _ = scorer.score(ann_fail)

    assert score_ok > score_fail, f"30인 미만({score_ok}) > 10인 미만({score_fail}) 이어야 함"
    print(f"[PASS] 직원 수 조건 테스트: 충족={score_ok:.1f}, 미충족={score_fail:.1f}")


def test_score_range():
    """점수는 항상 0~100 범위"""
    scorer = EligibilityScorer(COMPANY_PROFILE, {"use_llm": False})
    for i in range(5):
        ann = make_announcement(
            title=f"공고_{i}",
            raw_content="중소기업 AI R&D 디지털전환 벤처기업확인 서울 IT서비스 " * 3,
        )
        score, _ = scorer.score(ann)
        assert 0 <= score <= 100, f"점수 범위 초과: {score}"
    print("[PASS] 점수 범위 테스트")


if __name__ == "__main__":
    test_high_score_matching_announcement()
    test_low_score_unrelated_announcement()
    test_national_region_gives_region_score()
    test_employee_count_limit()
    test_score_range()
    print("\n✅ 모든 테스트 통과")
