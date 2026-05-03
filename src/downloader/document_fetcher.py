"""
문서 다운로더 - 적합 공고의 첨부파일을 자동 다운로드하고 표준 파일명으로 저장한다.
"""
import logging
import mimetypes
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

import requests


logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".pdf", ".hwp", ".hwpx", ".docx", ".xlsx", ".pptx", ".zip"}


class DocumentFetcher:
    """첨부파일 다운로더"""

    def __init__(self, config: dict):
        self.output_dir = Path(config.get("output_dir", "output/documents"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.supported_exts = set(config.get("supported_extensions", list(SUPPORTED_EXTS)))
        self.convert_hwp = config.get("convert_hwp_to_pdf", False)
        self.session = self._create_session()

    def download_all(self, site_name: str, announcement_title: str,
                     attachment_urls: List[str]) -> List[str]:
        """
        공고의 모든 첨부파일을 다운로드한다.

        Args:
            site_name: 사이트명 (폴더/파일명 prefix)
            announcement_title: 공고 제목
            attachment_urls: 첨부파일 URL 목록

        Returns:
            저장된 로컬 파일 경로 목록
        """
        saved_paths = []
        date_str = datetime.now().strftime("%Y%m%d")
        safe_title = self._sanitize_filename(announcement_title)[:60]
        safe_site = self._sanitize_filename(site_name)

        # 공고별 하위 폴더 생성
        folder = self.output_dir / f"{safe_site}_{safe_title}_{date_str}"
        folder.mkdir(parents=True, exist_ok=True)

        for url in attachment_urls:
            path = self._download_file(url, folder)
            if path:
                saved_paths.append(str(path))
                if self.convert_hwp and path.suffix.lower() == ".hwp":
                    pdf_path = self._convert_hwp_to_pdf(path)
                    if pdf_path:
                        saved_paths.append(str(pdf_path))

        logger.info("[%s] %s: 첨부파일 %d/%d개 다운로드",
                    site_name, announcement_title, len(saved_paths), len(attachment_urls))
        return saved_paths

    def _download_file(self, url: str, folder: Path) -> Optional[Path]:
        """단일 파일 다운로드"""
        try:
            resp = self.session.get(url, timeout=30, stream=True)
            resp.raise_for_status()

            filename = self._extract_filename(resp, url)
            ext = Path(filename).suffix.lower()

            if self.supported_exts and ext not in self.supported_exts:
                logger.debug("지원하지 않는 확장자, 건너뜀: %s", filename)
                return None

            save_path = folder / filename
            # 이름 충돌 방지
            counter = 1
            while save_path.exists():
                stem = Path(filename).stem
                save_path = folder / f"{stem}_{counter}{ext}"
                counter += 1

            with open(save_path, "wb") as fp:
                for chunk in resp.iter_content(chunk_size=8192):
                    fp.write(chunk)

            logger.debug("다운로드 완료: %s", save_path)
            return save_path

        except Exception as exc:
            logger.warning("다운로드 실패 (%s): %s", url, exc)
            return None

    @staticmethod
    def _extract_filename(response: requests.Response, url: str) -> str:
        """응답 헤더 또는 URL에서 파일명 추출"""
        # Content-Disposition 헤더 우선
        cd = response.headers.get("Content-Disposition", "")
        if cd:
            # RFC 5987 filename*= 처리
            match = re.search(r"filename\*=(?:UTF-8'')?([^\s;]+)", cd, re.IGNORECASE)
            if match:
                return unquote(match.group(1))
            match = re.search(r'filename=["\']?([^"\';\r\n]+)["\']?', cd, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                try:
                    return name.encode("latin-1").decode("utf-8")
                except (UnicodeDecodeError, UnicodeEncodeError):
                    return name

        # URL에서 파일명 추출
        parsed = urlparse(url)
        name = unquote(parsed.path.split("/")[-1])
        if "." in name:
            return name

        # Content-Type에서 확장자 추론
        ct = response.headers.get("Content-Type", "")
        ext = mimetypes.guess_extension(ct.split(";")[0].strip()) or ".bin"
        return f"attachment{ext}"

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """파일명에 사용할 수 없는 문자 제거"""
        name = unicodedata.normalize("NFC", name)
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        name = re.sub(r"\s+", "_", name.strip())
        return name or "unnamed"

    @staticmethod
    def _convert_hwp_to_pdf(hwp_path: Path) -> Optional[Path]:
        """LibreOffice CLI를 이용해 HWP → PDF 변환"""
        import subprocess
        try:
            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf",
                 "--outdir", str(hwp_path.parent), str(hwp_path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                pdf_path = hwp_path.with_suffix(".pdf")
                if pdf_path.exists():
                    return pdf_path
        except FileNotFoundError:
            logger.debug("LibreOffice가 설치되지 않아 HWP 변환을 건너뜁니다.")
        except Exception as exc:
            logger.warning("HWP 변환 실패 (%s): %s", hwp_path, exc)
        return None

    @staticmethod
    def _create_session() -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        })
        return session
