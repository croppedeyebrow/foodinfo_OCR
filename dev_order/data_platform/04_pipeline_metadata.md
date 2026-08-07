# 4단계 — 실행 이력·산출물·데이터 계보

## 목표

메모리에만 존재하는 실행 상태를 영속화하고 입력부터 Gold까지 추적 가능하게 한다.

## 메타데이터 모델

### pipeline_runs

- `run_id`
- `pipeline_name`
- `batch_id`
- `trigger_type`
- `status`
- `started_at`, `finished_at`
- `code_version`
- `config_hash`
- `error_summary`

### pipeline_steps

- `run_id`, `step_key`, `attempt`
- `status`
- `started_at`, `finished_at`
- `input_count`, `output_count`, `failed_count`
- `error_code`, `error_message`

### pipeline_artifacts

- `artifact_id`
- `run_id`, `step_key`
- `logical_name`
- `path`
- `format`
- `schema_version`
- `checksum`
- `row_count`, `byte_size`

### quality_results

- `run_id`, `artifact_id`
- `rule_id`, `severity`
- `passed`
- `observed_value`
- `details`

## 상태

```text
PENDING → RUNNING → SUCCEEDED
                  ↘ FAILED
                  ↘ PARTIAL
                  ↘ CANCELLED
```

## 구현 원칙

- 서비스 Backend DB와 pipeline metadata DB를 논리적으로 분리한다.
- 파일 본문을 PostgreSQL에 넣지 않는다.
- stack trace 전체 대신 오류코드·요약·로그 경로를 저장한다.
- `run_id`, artifact checksum으로 idempotency를 보장한다.
- Alembic 또는 동등한 migration으로 schema를 관리한다.

## 완료 조건

- Console/Dagster 재시작 후 실행 이력을 조회할 수 있다.
- Gold record에서 입력 batch와 artifact checksum까지 역추적할 수 있다.
- 동일 batch의 중복 publish가 식별된다.

## AI 지시문

```text
pipeline metadata 전용 모델과 migration, repository를 구현해.
서비스 Backend 테이블과 결합하지 말고 파일 payload를 DB에 저장하지 마.
Dagster 고유 metadata와 중복되는 필드는 adapter 경계를 명시해.
```
