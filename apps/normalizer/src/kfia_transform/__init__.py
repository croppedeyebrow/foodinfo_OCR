from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["run_kfia_bronze", "run_kfia_silver"]

if TYPE_CHECKING:
    from .bronze import KfiaBronzeBatchResult, run_kfia_bronze
    from .silver import KfiaSilverBatchResult, run_kfia_silver


def __getattr__(name: str):
    if name == "run_kfia_bronze":
        from .bronze import run_kfia_bronze

        return run_kfia_bronze
    if name == "run_kfia_silver":
        from .silver import run_kfia_silver

        return run_kfia_silver
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
