"""
범용 크롤러 - 사이트별 전용 파서가 없는 경우 사용하는 기본 크롤러
"""
import logging
import re
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base_crawler import Announcement, BaseCrawler


logger = logging.getLogger(__name__)


class GenericCrawler(BaseCrawler):
    """
    범용 공고 목록 크롤러.
    a 태그와 날짜 패턴을 기반으로 공고 목록을 추출한다.
    """

    DATE_PATTERN = re.compile(
        r"(\d{4}[\.\-/]\d{2}[\.\-/]\d{2})\s*[~\-]\s*(\d{4}[\.\-/]\d{2}[\.\-/]\d{2})"
    )

    def fetch_announcements(self) -> List[Announcement]:
        announcements = []
        try:
            resp = self.session.get(self.base_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # 테이블 행 또는 리스트 아이템에서 링크 추출
            candidates = soup.select("table tbody tr") or soup.select("ul li")

            for idx, row in enumerate(candidates[:30]):
                link = row.select_one("a[href]")
                if not link:
                    continue

                title = link.get_text(strip=True)
                if not title or len(title) < 4:
                    continue

                href = link.get("href", "")
                detail_url = urljoin(self.base_url, href)
                ann_id = f"{self.site_id}_{idx}_{hash(detail_url) & 0xFFFF:04x}"

                # 날짜 추출
                row_text = row.get_text()
                date_match = self.DATE_PATTERN.search(row_text)
                start_date = date_match.group(1) if date_match else None
                end_date = date_match.group(2) if date_match else None

                ann = Announcement(
                    site_id=self.site_id,
                    site_name=self.site_name,
                    announcement_id=ann_id,
                    title=title,
                    url=detail_url,
                    start_date=start_date,
                    end_date=end_date,
                )
                announcements.append(ann)

        except Exception as exc:
            self.logger.error("범용 크롤러 목록 수집 실패 (%s): %s", self.site_name, exc)

        return announcements

    def fetch_detail(self, announcement: Announcement) -> Announcement:
        try:
            resp = self.session.get(announcement.url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # 메인 콘텐츠 추출 (의미 있는 태그 순서대로 탐색)
            for selector in ["article", "div.content", "div.view", "div#content", "main"]:
                content_div = soup.select_one(selector)
                if content_div:
                    announcement.raw_content = content_div.get_text(separator="\n", strip=True)
                    announcement.description = announcement.raw_content[:500]
                    break

            # 첨부파일
            for link in soup.select("a[href]"):
                href = link.get("href", "")
                if any(ext in href.lower() for ext in [".pdf", ".hwp", ".docx", ".xlsx", "download"]):
                    file_url = urljoin(self.base_url, href)
                    if file_url not in announcement.attachments:
                        announcement.attachments.append(file_url)

        except Exception as exc:
            self.logger.warning("범용 크롤러 상세 수집 실패 (%s): %s", announcement.url, exc)

        return announcement
