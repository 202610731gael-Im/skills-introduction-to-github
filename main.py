"""
지원사업 공고 자동화 시스템 - 메인 실행 파일

사용법:
    python main.py                  # 즉시 1회 실행
    python main.py --schedule       # 매일 설정 시각에 자동 실행
    python main.py --schedule --now # 스케줄러 시작 + 즉시 1회 실행
"""
import argparse
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List

import yaml


# ────────────────────────────── 로그 설정 ────────────────────────────── #

def setup_logging(config: dict):
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    log_file = log_cfg.get("file", "logs/system.log")
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=log_cfg.get("max_bytes", 10_485_760),
            backupCount=log_cfg.get("backup_count", 5),
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


# ────────────────────────────── 설정 로드 ────────────────────────────── #

def load_config(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as fp:
        return yaml.safe_load(fp)


# ────────────────────────────── 핵심 파이프라인 ───────────────────────── #

def run_pipeline(config: dict):
    """
    전체 자동화 파이프라인을 1회 실행한다.
    1. 각 사이트 크롤링 → 신규 공고 수집
    2. 기업 적합성 점수 산출
    3. 70% 이상 공고 → 문서 다운로드
    4. 초안 생성
    5. 알림 발송
    """
    logger = logging.getLogger("pipeline")
    logger.info("=" * 60)
    logger.info("지원사업 공고 자동화 시스템 실행: %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    logger.info("=" * 60)

    from src.crawler.crawler_factory import get_crawler
    from src.db import Database
    from src.scorer import EligibilityScorer
    from src.downloader import DocumentFetcher
    from src.generator import DraftGenerator
    from src.notifier import EmailNotifier, SlackNotifier

    # 모듈 초기화
    db_path = config.get("database", {}).get("path", "data/announcements.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    company_profile = config.get("company_profile", {})
    eligibility_cfg = config.get("eligibility", {})
    openai_cfg = config.get("openai", {})

    scorer = EligibilityScorer(
        company_profile=company_profile,
        llm_config={**eligibility_cfg, **openai_cfg},
    )
    fetcher = DocumentFetcher(config.get("downloader", {}))
    generator = DraftGenerator(
        config=config.get("generator", {}),
        openai_config=openai_cfg,
        company_profile=company_profile,
    )
    email_notifier = EmailNotifier(config.get("email", {}))
    slack_notifier = SlackNotifier(config.get("slack", {}))

    min_score = eligibility_cfg.get("min_score_percent", 70.0)

    # ── STEP 1: 크롤링 ────────────────────────────────────────────────── #
    all_new_announcements = []
    sites = [s for s in config.get("sites", []) if s.get("enabled", True)]
    logger.info("모니터링 사이트 %d개", len(sites))

    for site_cfg in sites:
        crawler = get_crawler(site_cfg)
        announcements = crawler.run()

        new_count = 0
        for ann in announcements:
            if db.is_known(ann.site_id, ann.announcement_id):
                continue
            all_new_announcements.append(ann)
            new_count += 1

        logger.info("[%s] 신규 공고: %d건", site_cfg["name"], new_count)

    logger.info("전체 신규 공고: %d건", len(all_new_announcements))

    if not all_new_announcements:
        logger.info("신규 공고가 없습니다. 파이프라인 종료.")
        return

    # ── STEP 2: 적합도 점수 산출 ──────────────────────────────────────── #
    logger.info("적합도 분석 시작...")
    for ann in all_new_announcements:
        score, reason = scorer.score(ann)
        ann.eligibility_score = score
        ann.eligibility_reason = reason
        db.save(ann)

    high_score_anns = [a for a in all_new_announcements if a.eligibility_score >= min_score]
    logger.info("적합도 %.0f%% 이상 공고: %d건", min_score, len(high_score_anns))

    if not high_score_anns:
        logger.info("적합 공고가 없습니다. 알림만 발송합니다.")
        email_notifier.send_daily_report([])
        return

    # ── STEP 3 & 4: 문서 다운로드 + 초안 생성 ────────────────────────── #
    all_draft_paths: List[str] = []

    for ann in high_score_anns:
        logger.info("처리 중: [%.1f점] %s", ann.eligibility_score, ann.title)

        # 문서 다운로드
        downloaded = fetcher.download_all(
            site_name=ann.site_name,
            announcement_title=ann.title,
            attachment_urls=ann.attachments,
        )

        # 초안 생성
        draft_path = generator.generate(ann, downloaded)
        if draft_path:
            all_draft_paths.append(draft_path)

    # ── STEP 5: 알림 발송 ─────────────────────────────────────────────── #
    email_notifier.send_daily_report(high_score_anns, all_draft_paths)
    slack_notifier.send_daily_report(high_score_anns)

    logger.info("파이프라인 완료. 초안 파일 %d개 생성.", len(all_draft_paths))
    logger.info("=" * 60)


# ────────────────────────────── 스케줄러 ────────────────────────────── #

def start_scheduler(config: dict, run_now: bool = False):
    """APScheduler로 매일 지정 시각에 파이프라인을 실행한다."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("APScheduler가 설치되지 않았습니다. pip install APScheduler")
        sys.exit(1)

    scheduler_cfg = config.get("scheduler", {})
    run_time = scheduler_cfg.get("run_time", "07:00")
    timezone = scheduler_cfg.get("timezone", "Asia/Seoul")

    hour, minute = map(int, run_time.split(":"))

    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(
        func=run_pipeline,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
        args=[config],
        id="daily_pipeline",
        name="지원사업 공고 자동 수집",
        replace_existing=True,
    )

    logging.getLogger(__name__).info(
        "스케줄러 시작: 매일 %02d:%02d (%s) 실행", hour, minute, timezone
    )

    if run_now:
        logging.getLogger(__name__).info("즉시 1회 실행 후 스케줄러 대기...")
        run_pipeline(config)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("스케줄러 종료")


# ────────────────────────────── 진입점 ──────────────────────────────── #

def main():
    parser = argparse.ArgumentParser(description="지원사업 공고 자동화 시스템")
    parser.add_argument(
        "--config", default="config/settings.yaml",
        help="설정 파일 경로 (기본값: config/settings.yaml)",
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="스케줄러 모드 (매일 지정 시각에 자동 실행)",
    )
    parser.add_argument(
        "--now", action="store_true",
        help="즉시 1회 실행 (--schedule 없이 사용하거나 스케줄러 시작 시 함께 실행)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config)

    if args.schedule:
        start_scheduler(config, run_now=args.now)
    else:
        run_pipeline(config)


if __name__ == "__main__":
    main()
