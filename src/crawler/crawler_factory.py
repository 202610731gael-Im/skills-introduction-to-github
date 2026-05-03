"""
크롤러 팩토리 - site_config의 type에 따라 적절한 크롤러를 반환한다.
"""
from .base_crawler import BaseCrawler
from .bizinfo_crawler import BizinfoCrawler
from .kstartup_crawler import KStartupCrawler


def get_crawler(site_config: dict) -> BaseCrawler:
    """
    사이트 설정에 맞는 크롤러 인스턴스를 반환한다.

    Args:
        site_config: settings.yaml의 sites 항목

    Returns:
        BaseCrawler 하위 클래스 인스턴스

    Raises:
        ValueError: 지원하지 않는 사이트 type
    """
    crawler_map = {
        "bizinfo": BizinfoCrawler,
        "kstartup": KStartupCrawler,
    }

    site_type = site_config.get("type", "generic")
    crawler_class = crawler_map.get(site_type)

    if crawler_class is None:
        # 미지원 사이트는 기업마당 크롤러의 범용 모드로 대체
        from .generic_crawler import GenericCrawler
        return GenericCrawler(site_config)

    return crawler_class(site_config)
