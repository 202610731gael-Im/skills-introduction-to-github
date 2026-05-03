"""
기업마당(bizinfo.go.kr) 크롤러
"""
import logging
import re
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base_crawler import Announcement, BaseCrawler


logger = logging.getLogger(__name__)

BIZINFO_BASE = "https://www.bizinfo.go.kr"
LIST_URL = (
    "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/list.do"
    "?rows=20&cpage=1"
)


class BizinfoCrawler(BaseCrawler):
    """기업마당 지원사업 공고 크롤러"""

    def fetch_announcements(self) -> List[Announcement]:
        announcements = []
        try:
            resp = self.session.get(LIST_URL, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            rows = soup.select("table.tbl_list tbody tr")
            for row in rows:
                cols = row.select("td")
                if len(cols) < 5:
                    continue

                title_tag = row.select_one("td.subject a") or row.select_one("td a")
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                href = title_tag.get("href", "")
                detail_url = urljoin(BIZINFO_BASE, href)

                # 공고 ID: URL에서 추출
                ann_id_match = re.search(r"[?&]pDatacd=([^&]+)", href)
                ann_id = ann_id_match.group(1) if ann_id_match else href.split("/")[-1]

                # 기관명
                organization = cols[1].get_text(strip=True) if len(cols) > 1 else ""

                # 날짜 범위
                date_text = cols[-2].get_text(strip=True) if len(cols) > 2 else ""
                start_date, end_date = self._parse_date_range(date_text)

                ann = Announcement(
                    site_id=self.site_id,
                    site_name=self.site_name,
                    announcement_id=ann_id,
                    title=title,
                    url=detail_url,
                    organization=organization,
                    start_date=start_date,
                    end_date=end_date,
                )
                announcements.append(ann)

        except Exception as exc:
            self.logger.error("기업마당 목록 수집 실패: %s", exc)

        return announcements

    def fetch_detail(self, announcement: Announcement) -> Announcement:
        try:
            resp = self.session.get(announcement.url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # 공고 전문 텍스트
            content_div = (
                soup.select_one("div.view_cont")
                or soup.select_one("div.bbs_view")
                or soup.select_one("div#contents")
            )
            if content_div:
                announcement.raw_content = content_div.get_text(separator="\n", strip=True)
                announcement.description = announcement.raw_content[:500]

            # 지원 대상, 분야 등 메타 정보 파싱
            info_rows = soup.select("table.tbl_view tr")
            for row in info_rows:
                th = row.select_one("th")
                td = row.select_one("td")
                if not (th and td):
                    continue
                key = th.get_text(strip=True)
                val = td.get_text(strip=True)
                if "지원대상" in key:
                    announcement.target = val
                elif "지원분야" in key or "사업분야" in key:
                    announcement.category = val
                elif "지원금액" in key or "지원규모" in key:
                    announcement.support_amount = val
                elif "지역" in key:
                    announcement.region = val

            # 첨부파일
            file_links = soup.select("a[href*='download'], a[href*='.pdf'], a[href*='.hwp'], a[href*='.docx']")
            for link in file_links:
                file_url = urljoin(BIZINFO_BASE, link.get("href", ""))
                if file_url not in announcement.attachments:
                    announcement.attachments.append(file_url)

        except Exception as exc:
            self.logger.warning("기업마당 상세 수집 실패 (%s): %s", announcement.url, exc)

        return announcement

    @staticmethod
    def _parse_date_range(text: str):
        """'2024.01.01 ~ 2024.01.31' 형식의 날짜 파싱"""
        parts = re.split(r"\s*[~\-]\s*", text.strip())
        start = parts[0].strip() if len(parts) > 0 else None
        end = parts[1].strip() if len(parts) > 1 else None
        return start, end
