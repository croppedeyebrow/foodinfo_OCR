from .base import StageContext, StageExecutionResult, StageService
from .fixture_echo import FixtureEchoStage
from .kurly_bronze import KurlyBronzeStage
from .kurly_silver import KurlySilverStage

STAGE_REGISTRY: dict[str, StageService] = {
    KurlyBronzeStage.stage_key: KurlyBronzeStage(),
    KurlySilverStage.stage_key: KurlySilverStage(),
    FixtureEchoStage.stage_key: FixtureEchoStage(),
}

__all__ = [
    "FixtureEchoStage",
    "KurlyBronzeStage",
    "KurlySilverStage",
    "STAGE_REGISTRY",
    "StageContext",
    "StageExecutionResult",
    "StageService",
]
