"""Asset definitions and external graph specifications."""

from .collection import kurly_bronze_validated, kurly_collection_submission
from .future_graph import FUTURE_ASSET_SPECS

__all__ = [
    "FUTURE_ASSET_SPECS",
    "kurly_bronze_validated",
    "kurly_collection_submission",
]
