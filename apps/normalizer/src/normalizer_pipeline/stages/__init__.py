from .base import StageContext, StageExecutionResult, StageService
from .kfia_reference_bronze import KfiaReferenceBronzeStage
from .kfia_reference_silver import KfiaReferenceSilverStage
from .kurly_bronze import KurlyBronzeStage
from .kurly_silver import KurlySilverStage

STAGE_REGISTRY: dict[str, StageService] = {
    KurlyBronzeStage.stage_key: KurlyBronzeStage(),
    KurlySilverStage.stage_key: KurlySilverStage(),
    KfiaReferenceBronzeStage.stage_key: KfiaReferenceBronzeStage(),
    KfiaReferenceSilverStage.stage_key: KfiaReferenceSilverStage(),
}

__all__ = [
    "KfiaReferenceBronzeStage",
    "KfiaReferenceSilverStage",
    "KurlyBronzeStage",
    "KurlySilverStage",
    "STAGE_REGISTRY",
    "StageContext",
    "StageExecutionResult",
    "StageService",
]
