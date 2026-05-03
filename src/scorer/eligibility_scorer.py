"""
적합성 분석기 - 규칙 기반 점수 산출 + LLM 보조 분석
"""
import logging
import os
import re
from typing import Optional, Tuple

from ..crawler.base_crawler import Announcement


logger = logging.getLogger(__name__)


class EligibilityScorer:
    """
    기업 프로필과 공고 조건을 비교하여 적합도 점수(0~100)를 산출한다.
    1단계: 규칙 기반 점수 산출
    2단계: LLM(GPT) 보조 분석 (use_llm=True 시)
    """

    def __init__(self, company_profile: dict, llm_config: Optional[dict] = None):
        self.profile = company_profile
        self.llm_config = llm_config or {}
        self.use_llm = self.llm_config.get("use_llm", False)
        self._openai_client = None

    # ------------------------------------------------------------------ #
    # 공개 API                                                             #
    # ------------------------------------------------------------------ #

    def score(self, announcement: Announcement) -> Tuple[float, str]:
        """
        공고 적합도를 계산한다.

        Returns:
            (score: float 0~100, reason: str)
        """
        rule_score, rule_reason = self._rule_based_score(announcement)

        if self.use_llm and announcement.raw_content:
            try:
                llm_score, llm_reason = self._llm_score(announcement)
                # 규칙 기반 40% + LLM 60% 가중 평균
                final_score = rule_score * 0.4 + llm_score * 0.6
                reason = f"[규칙:{rule_score:.0f}점] {rule_reason}\n[LLM:{llm_score:.0f}점] {llm_reason}"
                return round(final_score, 1), reason
            except Exception as exc:
                logger.warning("LLM 분석 실패, 규칙 기반만 사용: %s", exc)

        return round(rule_score, 1), rule_reason

    # ------------------------------------------------------------------ #
    # 규칙 기반 점수 산출                                                   #
    # ------------------------------------------------------------------ #

    def _rule_based_score(self, ann: Announcement) -> Tuple[float, str]:
        """규칙 기반 점수 산출 (0~100)"""
        score = 0.0
        reasons = []
        full_text = " ".join([
            ann.title, ann.description, ann.raw_content,
            ann.target, ann.category, ann.organization,
        ]).lower()

        # 1) 기업 유형 일치 (25점)
        company_type = self.profile.get("company_type", "").lower()
        if company_type and company_type in full_text:
            score += 25
            reasons.append(f"기업유형({company_type}) 일치 +25")
        elif "중소기업" in full_text or "스타트업" in full_text:
            score += 15
            reasons.append("중소기업/스타트업 대상 +15")

        # 2) 업종/키워드 일치 (30점)
        keywords = self.profile.get("keywords", [])
        industry = self.profile.get("industry", "")
        sub_industry = self.profile.get("sub_industry", "")
        matched_kw = []
        for kw in [industry, sub_industry] + keywords:
            if kw and kw.lower() in full_text:
                matched_kw.append(kw)
        if matched_kw:
            kw_score = min(30, len(matched_kw) * 6)
            score += kw_score
            reasons.append(f"업종/키워드 {matched_kw} 일치 +{kw_score}")

        # 3) 지역 일치 (15점)
        region = self.profile.get("region", "")
        if not region or "전국" in full_text or "전체" in full_text:
            score += 15
            reasons.append("지역 제한 없음 +15")
        elif region in full_text:
            score += 15
            reasons.append(f"지역({region}) 일치 +15")
        else:
            reasons.append("지역 불일치 +0")

        # 4) 인증 보유 가산점 (10점)
        certs = self.profile.get("certifications", [])
        for cert in certs:
            if cert and cert.lower() in full_text:
                score += 5
                reasons.append(f"인증({cert}) 보유 가산 +5")
                if score >= 100:
                    break

        # 5) 직원/매출 규모 적합성 (20점)
        emp_count = self.profile.get("employee_count", 0)
        score += self._check_employee_match(full_text, emp_count, reasons)

        score = min(score, 100.0)
        return score, " | ".join(reasons) if reasons else "기준 미달"

    def _check_employee_match(self, text: str, emp_count: int, reasons: list) -> float:
        """직원 수 기반 규모 적합성 (0~20)"""
        # 직원 수 제한이 명시된 경우 파싱
        limit_match = re.search(r"(\d+)\s*인\s*(미만|이하|이상)", text)
        if not limit_match:
            reasons.append("직원 수 제한 없음 +20")
            return 20.0

        limit = int(limit_match.group(1))
        condition = limit_match.group(2)

        if condition in ("미만", "이하") and emp_count < limit:
            reasons.append(f"직원 수 조건({limit}인 {condition}) 충족 +20")
            return 20.0
        elif condition == "이상" and emp_count >= limit:
            reasons.append(f"직원 수 조건({limit}인 {condition}) 충족 +20")
            return 20.0
        else:
            reasons.append(f"직원 수 조건({limit}인 {condition}) 미충족 +0")
            return 0.0

    # ------------------------------------------------------------------ #
    # LLM 보조 분석                                                         #
    # ------------------------------------------------------------------ #

    def _llm_score(self, ann: Announcement) -> Tuple[float, str]:
        """GPT를 활용한 공고 적합도 분석"""
        client = self._get_openai_client()

        company_summary = (
            f"기업명: {self.profile.get('name', '')}\n"
            f"업종: {self.profile.get('industry', '')} / {self.profile.get('sub_industry', '')}\n"
            f"설립연도: {self.profile.get('established_year', '')}\n"
            f"직원 수: {self.profile.get('employee_count', '')}명\n"
            f"연매출: {self.profile.get('annual_revenue_million', '')}백만원\n"
            f"소재지: {self.profile.get('region', '')}\n"
            f"기업 유형: {self.profile.get('company_type', '')}\n"
            f"보유 인증: {', '.join(self.profile.get('certifications', []))}\n"
            f"관심 키워드: {', '.join(self.profile.get('keywords', []))}"
        )

        ann_summary = (
            f"공고 제목: {ann.title}\n"
            f"주관 기관: {ann.organization}\n"
            f"지원 대상: {ann.target}\n"
            f"지원 분야: {ann.category}\n"
            f"지원 금액: {ann.support_amount}\n"
            f"공고 내용:\n{ann.raw_content[:2000]}"
        )

        prompt = (
            "당신은 정부 지원사업 전문 컨설턴트입니다.\n"
            "아래 기업 정보와 지원사업 공고를 비교하여 이 기업이 해당 사업에 선정될 가능성을 "
            "0~100점으로 평가하고, 판단 근거를 한국어로 설명하세요.\n\n"
            f"[기업 정보]\n{company_summary}\n\n"
            f"[공고 정보]\n{ann_summary}\n\n"
            "응답 형식 (반드시 이 형식을 지켜주세요):\n"
            "점수: [0~100 사이의 숫자]\n"
            "근거: [판단 근거 설명]"
        )

        model = self.llm_config.get("llm_model", "gpt-4o")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3,
        )

        content = response.choices[0].message.content.strip()
        return self._parse_llm_response(content)

    @staticmethod
    def _parse_llm_response(content: str) -> Tuple[float, str]:
        """LLM 응답에서 점수와 근거 추출"""
        score_match = re.search(r"점수\s*:\s*(\d+(?:\.\d+)?)", content)
        reason_match = re.search(r"근거\s*:\s*(.+)", content, re.DOTALL)

        score = float(score_match.group(1)) if score_match else 50.0
        score = max(0.0, min(100.0, score))
        reason = reason_match.group(1).strip() if reason_match else content[:300]

        return score, reason

    def _get_openai_client(self):
        """OpenAI 클라이언트 반환 (지연 초기화)"""
        if self._openai_client is None:
            try:
                from openai import OpenAI
                api_key = (
                    self.llm_config.get("api_key")
                    or os.environ.get("OPENAI_API_KEY")
                )
                if not api_key:
                    raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
                self._openai_client = OpenAI(api_key=api_key)
            except ImportError as exc:
                raise ImportError("openai 패키지가 설치되지 않았습니다: pip install openai") from exc
        return self._openai_client
