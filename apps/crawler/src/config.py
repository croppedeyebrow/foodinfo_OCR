from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class CrawlerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    crawler_user_agent: str = "neulsom-kurly-ocr/0.1"
    crawler_request_interval_seconds: float = 2.0
    crawler_timeout_seconds: float = 30.0
    crawler_max_retries: int = 3
    crawler_headless: bool = True
    crawler_save_html: bool = False
    discovery_scroll_wait_ms: int = 1500
    discovery_unchanged_limit: int = 3


def load_settings() -> CrawlerSettings:
    return CrawlerSettings()
