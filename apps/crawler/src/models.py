from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class DiscoveryMode(str, Enum):
    URL_LIST = "URL_LIST"
    SEARCH = "SEARCH"
    CATEGORY = "CATEGORY"


class KurlyProductUrl(BaseModel):
    requested_url: HttpUrl
    product_id: str
    canonical_url: HttpUrl


class DiscoveredProduct(BaseModel):
    schema_version: str = "1.0"
    batch_id: str
    source_site: str = "KURLY"
    source_mode: DiscoveryMode
    source_value: str
    original_product_id: str
    product_name_preview: str | None = None
    product_url: HttpUrl
    discovery_order: int
    discovered_at: datetime
    discovery_status: str = "DISCOVERED"


class DiscoveryFailure(BaseModel):
    batch_id: str
    source_mode: DiscoveryMode
    source_value: str
    requested_url: str
    error_code: str
    error_message: str
    failed_at: datetime


class DiscoveryManifest(BaseModel):
    schema_version: str = "1.0"
    batch_id: str
    source_site: str = "KURLY"
    source_mode: DiscoveryMode
    source_value: str
    requested_url: str
    max_products: int | None = None
    max_scrolls: int | None = None
    discovered_count: int = 0
    duplicate_count: int = 0
    stop_reason: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "RUNNING"


class DownloadedImage(BaseModel):
    sequence: int
    source_url: str
    local_path: str
    local_name: str
    sha256: str
    alt: str | None = None
    width: int | None = None
    height: int | None = None
    skip_reason: str | None = None


class ImageCandidate(BaseModel):
    source_url: str
    alt: str | None = None
    width: int | None = None
    height: int | None = None
    dom_path: str | None = None


class CrawledProductRecord(BaseModel):
    schema_version: str = "1.0"
    batch_id: str
    source_site: str = "KURLY"
    original_product_id: str
    product_url: str
    requested_url: str
    product_name_raw: str | None = None
    food_name_candidate: str | None = None
    sales_unit_raw: str | None = None
    weight_raw: str | None = None
    quantity_raw: str | None = None
    expiration_info_dom: str | None = None
    storage_method_dom: str | None = None
    storage_type_dom: str = "UNKNOWN"
    detail_image_urls: list[str] = Field(default_factory=list)
    downloaded_images: list[DownloadedImage] = Field(default_factory=list)
    page_text: str | None = None
    collected_at: datetime
    crawl_status: str = "COMPLETED"
    image_candidates: list[ImageCandidate] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class CrawlFailureRecord(BaseModel):
    batch_id: str
    source_site: str = "KURLY"
    original_product_id: str = ""
    product_url: str = ""
    requested_url: str = ""
    error_code: str
    error_message: str
    failed_at: datetime


class ManifestRow(BaseModel):
    batch_id: str
    original_product_id: str
    product_name: str
    product_url: str
    image_path: str = ""
    source_image_url: str = ""
    source_site: str = "KURLY"
    expiration_info_dom: str = ""
    storage_method_dom: str = ""
    storage_type_dom: str = ""
    food_name_candidate: str = ""
    weight_raw: str = ""
    quantity_raw: str = ""
    sales_unit_raw: str = ""
