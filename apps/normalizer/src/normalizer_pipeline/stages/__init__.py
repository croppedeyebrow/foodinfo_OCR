from .base import StageContext, StageExecutionResult, StageService
from .gold_freshness_publish import GoldFreshnessPublishStage
from .kfia_reference_bronze import KfiaReferenceBronzeStage
from .kfia_reference_silver import KfiaReferenceSilverStage
from .kurly_bronze import KurlyBronzeStage
from .kurly_kfia_reconcile import KurlyKfiaReconcileStage
from .kurly_silver import KurlySilverStage

STAGE_REGISTRY: dict[str, StageService] = {
    KurlyBronzeStage.stage_key: KurlyBronzeStage(),
    KurlySilverStage.stage_key: KurlySilverStage(),
    KfiaReferenceBronzeStage.stage_key: KfiaReferenceBronzeStage(),
    KfiaReferenceSilverStage.stage_key: KfiaReferenceSilverStage(),
    KurlyKfiaReconcileStage.stage_key: KurlyKfiaReconcileStage(),
    GoldFreshnessPublishStage.stage_key: GoldFreshnessPublishStage(),
}

__all__ = [
    "GoldFreshnessPublishStage",
    "KfiaReferenceBronzeStage",
    "KfiaReferenceSilverStage",
    "KurlyBronzeStage",
    "KurlyKfiaReconcileStage",
    "KurlySilverStage",
    "STAGE_REGISTRY",
    "StageContext",
    "StageExecutionResult",
    "StageService",
]
