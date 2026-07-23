from __future__ import annotations

from .base import DiscoveryError, DiscoveryResult, ensure_fresh_batch_dir
from .url_list import UrlListProductDiscovery

__all__ = [
    "CategoryProductDiscovery",
    "DiscoveryError",
    "DiscoveryResult",
    "SearchProductDiscovery",
    "UrlListProductDiscovery",
    "ensure_fresh_batch_dir",
]


def __getattr__(name: str):
    if name == "SearchProductDiscovery":
        from .search import SearchProductDiscovery

        return SearchProductDiscovery
    if name == "CategoryProductDiscovery":
        from .category import CategoryProductDiscovery

        return CategoryProductDiscovery
    raise AttributeError(name)
