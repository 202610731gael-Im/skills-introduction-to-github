"""
크롤러 기본 클래스 - 모든 사이트별 크롤러의 공통 인터페이스 정의
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


logger = logging.getLogger(__name__)


@dataclass
class Announcement:
    """공고 정보 표준 스키마"""
    site_id: str                          # 사이트 식별자
    site_name: str                        # 사이트명
    announcement_id: str                  # 원본 사이트의 공고 ID
    title: str                            # 공고 제목
    url: str                              # 공고 상세 URL
    organization: str = ""               # 주관 기관
    category: str = ""                   # 지원 분야/유형
    target: str = ""                     # 지원 대상
    region: str = ""                     # 지원 지역
    support_amount: str = ""             # 지원 금액
    start_date: Optional[str] = None     # 접수 시작일
    end_date: Optional[str] = None       # 접수 마감일
    description: str = ""               # 공고 설명 요약
    attachments: List[str] = field(default_factory=list)  # 첨부파일 URL 목록
    raw_content: str = ""               # 공고 전문 (텍스트)
    collected_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    eligibility_score: float = 0.0      # 적합도 점수 (0~100)
    eligibility_reason: str = ""        # 적합도 판단 근거


class BaseCrawler(ABC):
    """
    사이트별 크롤러의 기본 클래스.
    새 사이트를 추가하려면 이 클래스를 상속하여 구현한다.
    """

    def __init__(self, site_config: dict):
        """
        Args:
            site_config: settings.yaml의 sites 항목 중 하나
        """
        self.site_id = site_config["id"]
        self.site_name = site_config["name"]
        self.base_url = site_config["url"]
        self.logger = logging.getLogger(f"{__name__}.{self.site_id}")
        self.session = self._create_session()

    def _create_session(self):
        """requests 세션 생성 (공통 헤더 설정)"""
        import requests
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9",
        })
        return session

    @abstractmethod
    def fetch_announcements(self) -> List[Announcement]:
        """
        사이트에서 공고 목록을 가져온다.

        Returns:
            Announcement 객체 리스트
        """

    @abstractmethod
    def fetch_detail(self, announcement: Announcement) -> Announcement:
        """
        공고 상세 페이지에서 전문 및 첨부파일 URL을 수집한다.

        Args:
            announcement: 기본 정보가 담긴 Announcement 객체

        Returns:
            상세 정보가 추가된 Announcement 객체
        """

    def run(self) -> List[Announcement]:
        """
        공고 목록 수집 → 상세 정보 수집 파이프라인 실행

        Returns:
            상세 정보가 포함된 Announcement 리스트
        """
        self.logger.info("[%s] 공고 수집 시작", self.site_name)
        try:
            announcements = self.fetch_announcements()
            self.logger.info("[%s] 공고 %d건 발견", self.site_name, len(announcements))

            detailed = []
            for ann in announcements:
                try:
                    detailed.append(self.fetch_detail(ann))
                except Exception as exc:
                    self.logger.warning(
                        "[%s] 상세 수집 실패 (id=%s): %s",
                        self.site_name, ann.announcement_id, exc,
                    )
                    detailed.append(ann)

            return detailed

        except Exception as exc:
            self.logger.error("[%s] 공고 수집 오류: %s", self.site_name, exc)
            return []
