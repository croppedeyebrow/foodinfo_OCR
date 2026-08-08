# Pipeline Metadata와 Lineage

## 추적 대상

- pipeline run
- 단계별 실행과 attempt
- 입력·출력 artifact
- schema/code/rule version
- checksum, row count, byte size
- 품질검사 결과
- Gold publish history

## 원칙

- 서비스 Backend DB와 pipeline metadata를 논리적으로 분리한다.
- 파일 payload 전체를 PostgreSQL에 넣지 않는다.
- 모든 Gold 결과에서 입력 batch와 artifact checksum을 역추적할 수 있어야 한다.
- 동일 batch·dataset version은 idempotent하게 처리한다.

## 구현

PostgreSQL의 전용 `pipeline_metadata` schema를 사용한다. 서비스 Backend
테이블과 namespace를 공유하지 않으며 파일 본문은 저장하지 않는다.

| 테이블 | 역할 |
|---|---|
| `schema_migrations` | 적용 migration version/checksum |
| `pipeline_runs` | pipeline/batch/trigger/status/code/config |
| `pipeline_steps` | step별 attempt·상태·입출력/실패 수 |
| `pipeline_artifacts` | 파일 경로·형식·schema/checksum·행/byte 수 |
| `pipeline_artifact_lineage` | parent→child artifact 관계 |
| `quality_results` | rule·severity·pass 여부·제한된 JSON details |

구현 위치:

- 모델: `apps/normalizer/src/metadata/models.py`
- migration: `apps/normalizer/src/metadata/migrations/`
- repository: `apps/normalizer/src/metadata/repository.py`
- Collection adapter: `apps/normalizer/src/metadata/submission_adapter.py`
- Dagster 경계: `apps/normalizer/src/metadata/dagster_adapter.py`

## 실행

```bash
docker compose up -d postgres
docker compose run --rm normalizer python -m src.cli metadata-migrate

docker compose run --rm normalizer python -m src.cli metadata-register-submission \
  --batch-id 20260808-jaeseong-001 \
  --member jaeseong \
  --code-version <git-sha>

docker compose run --rm normalizer python -m src.cli metadata-list-runs \
  --batch-id 20260808-jaeseong-001
```

조회 명령은 `metadata-show-run`, `metadata-lineage`도 제공한다. 팀원 Console에는
DB 조회·migration·quality·publish 기능을 노출하지 않는다.

## Idempotency

- `run_id`: accepted manifest의 batch ID와 `content_hash`로 결정한다.
- artifact: run/step/logical name/checksum unique key로 중복 등록을 방지한다.
- migration: version과 SQL checksum을 기록하며 적용된 SQL 변경을 거부한다.

## Dagster adapter 경계

stage 05에서는 Dagster 객체를 repository에 전달하지 않는다.
`dagster_adapter.py`가 Dagster run ID를 일반 run metadata로 바꾸고,
artifact를 primitive materialization metadata로 변환한다.

## Migration과 rollback

- 적용: `metadata-migrate` (transaction + PostgreSQL advisory lock)
- rollback SQL: `0001_pipeline_metadata.down.sql`
- rollback은 metadata schema를 삭제하므로 writer 중지·backup 후 관리자가
  명시적으로 실행한다. routine test에서는 실행하지 않는다.
