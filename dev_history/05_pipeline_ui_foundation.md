# 5단계 — UI 기반 Pipeline Stage 실행 기반

- **지시 문서**: `dev_order_docs/05_pipeline_ui_foundation.md`
- **완료일**: 2026-08-30
- **상태**: DONE

## 결과 요약

Console에서 Dagster UI·job 대신 **`PipelineService` + REST API + `/steps/pipeline` 화면**으로 Stage를 실행·조회·재시도할 수 있는 기반을 구현했다. `fixture_echo` Stage로 end-to-end 검증이 가능하며, 중복 실행 방지·실패 후 retry·백그라운드 실행·상태 폴링이 동작한다.

## 변경 파일과 이유

| 영역 | 주요 파일 | 이유 |
|---|---|---|
| Normalizer 파이프라인 | `apps/normalizer/src/normalizer_pipeline/service.py` | run 생성·실행·배치 상태·retry |
| Normalizer 파이프라인 | `apps/normalizer/src/normalizer_pipeline/store.py` | InMemory store + `MetadataRepository` 분기 |
| Normalizer Stage | `apps/normalizer/src/normalizer_pipeline/stages/fixture_echo.py` | fixture artifact 생성·검증용 Stage |
| Console 게이트웨이 | `apps/console/src/pipeline_gateway.py` | normalizer 로드·백그라운드 실행·sys.path 복구 |
| Console API/UI | `apps/console/src/main.py` | `/steps/pipeline`, pipeline REST API, `/steps/platform` → redirect |
| Console UI | `step_pipeline.html`, `partials/pipeline_status.html` | Stage 실행·2초 폴링·상태 표시 |
| Console runner | `apps/console/src/runner.py` | Dagster intake·platform-pipeline command 제거 |
| Console 의존성 | `apps/console/requirements.txt` | pydantic·jsonschema·psycopg (metadata 선택) |
| 테스트 | `tests/test_pipeline_service.py`, `tests/test_console.py` | 서비스·API·역할·리다이렉트 |
| 테스트 헬퍼 | `tests/conftest.py` | `use_console()` 경로 복구 |
| gitignore | `.gitignore` | `datasets/pipeline/*` fixture 산출물 제외 |

## UI 및 데이터 흐름 변화

### 변경 전 → 변경 후

```text
[이전] OPERATOR → /steps/platform (Dagster intake UI)
              → POST /jobs/dagster-intake, /jobs/platform-pipeline

[이후] OPERATOR → /steps/pipeline (6. 파이프라인)
              → POST /api/pipeline/batches/{batch_id}/stages/{stage}/runs
              → GET  /api/pipeline/batches/{batch_id}/status (HTMX 2초 폴링)
              → POST /api/pipeline/runs/{run_id}/retry
```

### 실행 흐름

```text
Browser → Console API → PipelineService.start_run (PENDING)
                     → schedule_run_execution (background thread)
                     → PipelineService.execute_run → StageService
                     → Metadata store (InMemory 또는 PostgreSQL)
                     → Artifact (예: datasets/pipeline/fixture/{batch_id}/echo.json)
```

## 계약·환경변수·migration 변화

- `DATABASE_URL` — 설정 시 PostgreSQL `MetadataRepository`, 미설정 시 InMemory (로컬·테스트)
- `PIPELINE_CODE_VERSION` — run metadata `code_version` (기본 `dev`)
- 기존 accepted 배치·manifest·submission 계약 변경 없음

## 실행한 테스트와 결과

```text
pytest tests/test_pipeline_service.py tests/test_console.py -q
# 41 passed

pytest -q
# 124 passed, 2 skipped, 2 failed (psycopg 미설치 환경의 integration 테스트 — 기존과 동일)
```

## 기존 기능 호환성

- COLLECTOR 수집·OCR UI (`/steps/discover` ~ `/steps/ocr`) 회귀 없음
- 4단계 검증·제출 (`/steps/submit`) 유지
- `/steps/platform` — **307 redirect** → `/steps/pipeline` (북마크 호환)
- `platform_mode` 설정·레거시 `CONSOLE_PLATFORM_MODE` 플래그 유지

## 보안·성능·데이터 안전 고려

- pipeline API·UI는 **OPERATOR 전용** (`403` for COLLECTOR)
- 배치 allowlist는 4단계와 동일 (`resolve_operator_batch`)
- 동일 batch·stage에 **ACTIVE run 중복 생성 거부** (`DuplicateRunError`)
- 프로세스 재시작 시 `RUNNING` → `FAILED` 복구 (`recover_stale_runs`)
- fixture artifact는 `datasets/pipeline/` 하위에만 기록 (immutable raw 입력 미변경)

## 잔여 과제·다음 단계 진입 조건

- **6단계** `06_kurly_bronze_silver.md`: Kurly Bronze·Silver Stage를 `STAGE_REGISTRY`에 등록
- 실제 Stage는 `fixture_echo` 외 아직 없음 — 6·7단계에서 추가
- PostgreSQL integration 테스트는 로컬에 `psycopg` 설치 또는 `DATABASE_URL` 환경에서 실행

## 레거시·주의사항

- **Dagster 물리 제거는 11단계** (`orchestration/`, `compose.yaml` dagster 서비스, `start_console.py --platform` 등은 아직 존재)
- Console에서 Dagster **UI·job route만 제거**함 — orchestration 코드는 테스트·Docker에서 참조 가능

## 운영 핫픽스 (2026-08-30)

| 이슈 | 원인 | 수정 |
|---|---|---|
| 파이프라인 UI 빨간 `3` | Docker에서 `parents[3]` 즉시 평가 → `IndexError: 3` | `pipeline_gateway._normalizer_candidates()` 안전 경로 |
| `src` 패키지 충돌 | console·normalizer 둘 다 `src` 사용 | `_import_normalizer_pipeline()` 격리 import |
| postgres 미기동 | `DATABASE_URL` 있는데 DB만 중지 | `compose.yaml` `console depends_on postgres` |
| Console 이미지 의존성 | polars가 console 이미지에 없음 | `docker/console.Dockerfile`에 normalizer requirements 병합 |
