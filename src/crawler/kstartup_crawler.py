"""
K-스타트업(k-startup.go.kr) 크롤러
"""
import logging
import re
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base_crawler import Announcement, BaseCrawler


logger = logging.getLogger(__name__)

KSTARTUP_BASE = "https://www.k-startup.go.kr"
LIST_URL = (
    "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"
    "?schM=list&page=1&perPage=20&bizpbancSn=&pbancEndYn=N"
)


class KStartupCrawler(BaseCrawler):
    """K-스타트업 지원사업 공고 크롤러"""

    def fetch_announcements(self) -> List[Announcement]:
        announcements = []
        try:
            resp = self.session.get(LIST_URL, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            items = (
                soup.select("ul.business_list li")
                or soup.select("div.list_wrap ul li")
                or soup.select("table tbody tr")
            )

            for item in items:
                title_tag = item.select_one("a.tit") or item.select_one("strong.tit") or item.select_one("a")
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                href = title_tag.get("href", "")
                detail_url = urljoin(KSTARTUP_BASE, href)

                # 공고 ID 추출
                ann_id_match = re.search(r"bizpbancSn=(\d+)", href)
                ann_id = ann_id_match.group(1) if ann_id_match else title[:20]

                # 기관명
                org_tag = item.select_one("span.organ") or item.select_one("span.agency")
                organization = org_tag.get_text(strip=True) if org_tag else ""

                # 날짜
                date_tag = item.select_one("span.date") or item.select_one("dd.date")
                start_date, end_date = None, None
                if date_tag:
                    start_date, end_date = self._parse_date_range(date_tag.get_text(strip=True))

                # 카테고리
                category_tag = item.select_one("span.cate") or item.select_one("em.category")
                category = category_tag.get_text(strip=True) if category_tag else ""

                ann = Announcement(
                    site_id=self.site_id,
                    site_name=self.site_name,
                    announcement_id=ann_id,
                    title=title,
                    url=detail_url,
                    organization=organization,
                    category=category,
                    start_date=start_date,
                    end_date=end_date,
                )
                announcements.append(ann)

        except Exception as exc:
            self.logger.error("K-스타트업 목록 수집 실패: %s", exc)

        return announcements

    def fetch_detail(self, announcement: Announcement) -> Announcement:
        try:
            resp = self.session.get(announcement.url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # 공고 전문
            content_div = (
                soup.select_one("div.view_content")
                or soup.select_one("div.cont_box")
                or soup.select_one("article")
            )
            if content_div:
                announcement.raw_content = content_div.get_text(separator="\n", strip=True)
                announcement.description = announcement.raw_content[:500]

            # 메타 정보
            detail_rows = soup.select("dl dt, dl dd, table tr")
            for row in detail_rows:
                th = row.select_one("th")
                td = row.select_one("td")
                if not (th and td):
                    continue
                key = th.get_text(strip=True)
                val = td.get_text(strip=True)
                if "지원대상" in key:
                    announcement.target = val
                elif "지원분야" in key:
                    announcement.category = val
                elif "지원금액" in key or "지원규모" in key:
                    announcement.support_amount = val

            # 첨부파일
            file_links = soup.select(
                "a[href*='download'], a[href*='.pdf'], a[href*='.hwp'], a[href*='.docx']"
            )
            for link in file_links:
                file_url = urljoin(KSTARTUP_BASE, link.get("href", ""))
                if file_url not in announcement.attachments:
                    announcement.attachments.append(file_url)

        except Exception as exc:
            self.logger.warning("K-스타트업 상세 수집 실패 (%s): %s", announcement.url, exc)

        return announcement

    @staticmethod
    def _parse_date_range(text: str):
        """날짜 범위 파싱"""
        parts = re.split(r"\s*[~\-]\s*", text.strip())
        start = parts[0].strip() if len(parts) > 0 else None
        end = parts[1].strip() if len(parts) > 1 else None
        return start, end
