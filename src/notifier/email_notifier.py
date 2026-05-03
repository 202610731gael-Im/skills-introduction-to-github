"""
알림 모듈 - 이메일 및 슬랙으로 적합 공고 알림 발송
"""
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from ..crawler.base_crawler import Announcement


logger = logging.getLogger(__name__)


class EmailNotifier:
    """이메일 알림 발송기"""

    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.smtp_host = config.get("smtp_host", "smtp.gmail.com")
        self.smtp_port = config.get("smtp_port", 587)
        self.sender = config.get("sender", "")
        self.password = config.get("password") or os.environ.get("EMAIL_PASSWORD", "")
        self.recipients = config.get("recipients", [])

    def send_daily_report(self, announcements: List[Announcement],
                          draft_paths: Optional[List[str]] = None) -> bool:
        """
        오늘 수집된 고적합도 공고를 이메일로 발송한다.

        Args:
            announcements: 발송할 공고 목록 (이미 점수 필터 완료)
            draft_paths: 생성된 초안 파일 경로 목록

        Returns:
            발송 성공 여부
        """
        if not self.enabled:
            logger.debug("이메일 알림이 비활성화 상태입니다.")
            return False

        if not announcements:
            logger.info("발송할 고적합도 공고가 없습니다.")
            return True

        subject = (
            f"[지원사업 자동화] {datetime.now().strftime('%Y-%m-%d')} "
            f"적합 공고 {len(announcements)}건"
        )
        body = self._build_html_body(announcements, draft_paths or [])

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = ", ".join(self.recipients)
            msg.attach(MIMEText(body, "html", "utf-8"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self.sender, self.password)
                smtp.sendmail(self.sender, self.recipients, msg.as_string())

            logger.info("이메일 발송 완료: %s", self.recipients)
            return True

        except Exception as exc:
            logger.error("이메일 발송 실패: %s", exc)
            return False

    @staticmethod
    def _build_html_body(announcements: List[Announcement], draft_paths: List[str]) -> str:
        date_str = datetime.now().strftime("%Y년 %m월 %d일")
        rows = ""
        for ann in announcements:
            score_color = "#28a745" if ann.eligibility_score >= 80 else "#ffc107"
            rows += f"""
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">{ann.site_name}</td>
                <td style="padding:8px;border:1px solid #ddd;">
                    <a href="{ann.url}" style="color:#0366d6;">{ann.title}</a>
                </td>
                <td style="padding:8px;border:1px solid #ddd;">{ann.organization}</td>
                <td style="padding:8px;border:1px solid #ddd;">{ann.support_amount}</td>
                <td style="padding:8px;border:1px solid #ddd;text-align:center;">
                    <span style="color:{score_color};font-weight:bold;">
                        {ann.eligibility_score:.1f}점
                    </span>
                </td>
                <td style="padding:8px;border:1px solid #ddd;">{ann.end_date or '-'}</td>
            </tr>"""

        draft_list = ""
        if draft_paths:
            draft_list = "<ul>" + "".join(f"<li>{p}</li>" for p in draft_paths) + "</ul>"

        return f"""
        <html><body style="font-family:Malgun Gothic,sans-serif;color:#333;">
        <h2 style="color:#0366d6;">📋 {date_str} 지원사업 공고 자동 분석 결과</h2>
        <p>적합도 70% 이상 공고 <strong>{len(announcements)}건</strong>이 발견되었습니다.</p>
        <table style="border-collapse:collapse;width:100%;margin-top:16px;">
            <thead>
                <tr style="background:#f6f8fa;">
                    <th style="padding:8px;border:1px solid #ddd;">사이트</th>
                    <th style="padding:8px;border:1px solid #ddd;">공고명</th>
                    <th style="padding:8px;border:1px solid #ddd;">주관기관</th>
                    <th style="padding:8px;border:1px solid #ddd;">지원금액</th>
                    <th style="padding:8px;border:1px solid #ddd;">적합도</th>
                    <th style="padding:8px;border:1px solid #ddd;">마감일</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        {"<h3>생성된 초안 파일</h3>" + draft_list if draft_paths else ""}
        <hr><p style="font-size:12px;color:#666;">이 메일은 지원사업 공고 자동화 시스템이 발송했습니다.</p>
        </body></html>
        """


class SlackNotifier:
    """슬랙 웹훅 알림 발송기"""

    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.webhook_url = (
            config.get("webhook_url")
            or os.environ.get("SLACK_WEBHOOK_URL", "")
        )

    def send_daily_report(self, announcements: List[Announcement]) -> bool:
        if not self.enabled or not self.webhook_url:
            return False
        if not announcements:
            return True
        try:
            import urllib.request
            import json

            date_str = datetime.now().strftime("%Y-%m-%d")
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"📋 {date_str} 지원사업 공고 분석"},
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"적합도 70% 이상 공고 *{len(announcements)}건* 발견",
                    },
                },
            ]

            for ann in announcements[:10]:  # 최대 10건
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*<{ann.url}|{ann.title}>*\n"
                            f"기관: {ann.organization} | 금액: {ann.support_amount} | "
                            f"적합도: {ann.eligibility_score:.1f}점 | 마감: {ann.end_date or '-'}"
                        ),
                    },
                })

            payload = json.dumps({"blocks": blocks}).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            logger.info("슬랙 알림 발송 완료")
            return True
        except Exception as exc:
            logger.error("슬랙 알림 실패: %s", exc)
            return False
