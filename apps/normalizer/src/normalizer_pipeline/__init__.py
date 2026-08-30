"""Console-driven pipeline stage execution (Dagster replacement)."""

from .service import PipelineService
from .stages import STAGE_REGISTRY

__all__ = ["PipelineService", "STAGE_REGISTRY"]
