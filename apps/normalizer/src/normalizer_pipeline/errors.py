"""Pipeline execution errors surfaced to Console API."""


class PipelineError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class UnknownStageError(PipelineError):
    def __init__(self, stage_key: str) -> None:
        super().__init__("UNKNOWN_STAGE", f"알 수 없는 stage입니다: {stage_key}")


class PrerequisiteError(PipelineError):
    def __init__(self, message: str) -> None:
        super().__init__("PREREQUISITE_NOT_MET", message)


class DuplicateRunError(PipelineError):
    def __init__(self, batch_id: str, stage_key: str) -> None:
        super().__init__(
            "DUPLICATE_RUN",
            f"이미 실행 중이거나 대기 중인 stage입니다: {batch_id}/{stage_key}",
        )


class RunNotFoundError(PipelineError):
    def __init__(self, run_id: str) -> None:
        super().__init__("RUN_NOT_FOUND", f"run을 찾을 수 없습니다: {run_id}")


class RetryNotAllowedError(PipelineError):
    def __init__(self, message: str) -> None:
        super().__init__("RETRY_NOT_ALLOWED", message)
