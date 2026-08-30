# 3단계 — 실행 이력·Artifact·Lineage

- **지시 문서**: `dev_order_docs/03_pipeline_metadata.md`
- **완료일**: 2026-08
- **상태**: DONE

## 결과 요약

PostgreSQL `pipeline_metadata` 스키마에 **run·step·artifact·lineage·quality** 메타데이터를 기록하는 repository를 구춡했다. Dagster 없이도 실행 이력을 DB에 남길 수 있는 기반이다.

## 변경 파일과 이유

| 영역 | 주요 파일 | 이유 |
|---|---|---|
| Migration | `apps/normalizer/src/metadata/migrations/0001_pipeline_metadata.up.sql` | 테이블·인덱스·제약 |
| Models | `apps/normalizer/src/metadata/models.py` | Pydantic 타입·상태 전이 규칙 |
| Repository | `apps/normalizer/src/metadata/repository.py` | CRUD·멱등·상태 전이 |
| Adapter | `apps/normalizer/src/metadata/submission_adapter.py` | accepted bundle → metadata 등록 |
| Adapter | `apps/normalizer/src/metadata/dagster_adapter.py` | **레거시** Dagster 연동 (신규 코드 미사용 원칙) |
| Docker | `compose.yaml` `postgres` 서비스 | 로컬 pipeline DB |
| 테스트 | `tests/test_metadata_models.py` | 모델·migration discovery |
| 테스트 | `tests/test_pipeline_metadata_integration.py` | Postgres 통합·멱등 rerun |

## UI 및 데이터 흐름 변화

```text
accepted manifest  →  register_accepted_submission()
                           → pipeline_runs
                           → pipeline_steps
                           → pipeline_artifacts
                           → pipeline_artifact_lineage
```

3단계 시점에는 **Console UI에서 metadata 조회 화면은 없음**. CLI/adapter 경로로 기록. UI 조회는 5·9단계에서 확장 예정.

## 계약·환경변수·migration 변화

### 테이블

| 테이블 | 역할 |
|---|---|
| `pipeline_runs` | 배치/dataset 실행 |
| `pipeline_steps` | Stage별 attempt |
| `pipeline_artifacts` | 경로·checksum·row count |
| `pipeline_artifact_lineage` | parent → child |
| `quality_results` | rule별 품질 (후속 단계) |
| `schema_migrations` | migration 이력 |

### 환경변수

```env
DATABASE_URL=postgresql://freshness:local-password@postgres:5432/freshness
PIPELINE_CODE_VERSION=dev
```

### 멱등키 (설계)

```text
stage + input_checksum + contract_version + code_version + rule_version
```

## 실행한 테스트와 결과

```text
tests/test_metadata_models.py
tests/test_pipeline_metadata_integration.py  — Postgres fixture, partition rerun 멱등
```

## 기존 기능 호환성

- DB에 원본 파일 payload 저장하지 않음 (경로·checksum만).
- 기존 filesystem accepted 구조와 병행.

## 보안·성능·데이터 안전 고려

- Backend DB와 분리된 `pipeline_metadata` 스키마.
- 상태 전이 `PENDING → RUNNING → SUCCEEDED|FAILED` 검증.

## 잔여 과제·다음 단계 진입 조건

- [x] repository·migration 동작
- [x] accepted submission intake metadata 등록
- [ ] `PipelineService`가 run/step 기록 호출 — **5단계**
- [ ] UI에서 run ID 조회 — **5·9단계**
- → **4단계** 운영자 제출 UI

## 레거시·주의사항

- `dagster_adapter.py`·`tests/test_orchestration.py`는 **구 Dagster 주기 산출물**.
- `dev_order_docs` 원칙: 새 코드에서 dagster adapter **사용 금지**, 11단계에서 제거.
- `orchestration/` 패키지 전체가 동일 레거시 범주.
