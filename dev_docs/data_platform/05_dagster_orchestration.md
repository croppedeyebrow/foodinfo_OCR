# Dagster 오케스트레이션

## 책임 경계

Dagster는 asset 의존관계, partition 실행, 재시도, materialization metadata만
관리한다. 계약 검증과 metadata 등록은 `apps/normalizer`의 public Python
경계를 호출하며 변환·보정·품질 업무 규칙은 orchestration 코드에 두지 않는다.

Collection과 OCR 결과는 Dagster가 직접 생성하지 않는다.
`datasets/inbox/accepted/{batch_id}/manifest.json`을 외부 제출 결과로 읽는다.

## 현재 실행 가능한 asset

```text
kurly_collection_submission
  → kurly_bronze_validated
```

- partition: `collection_batches` dynamic partition (`batch_id`)
- `kurly_collection_submission`: accepted manifest 계약·checksum을 검증하고
  `ArtifactReference`만 반환
- `kurly_bronze_validated`: normalizer metadata adapter를 호출해 PostgreSQL에
  artifact와 lineage를 멱등 등록
- DB I/O asset에만 최대 2회 exponential retry 적용

Stage 06~10에서 구현할 asset은 `AssetSpec`으로 전체 그래프에 표시한다.
이 spec은 실행 가능한 가짜 산출물을 만들지 않는다.

## Resource

- `ArtifactStoreResource`: accepted batch 탐색과 manifest reference
- `PipelineMetadataResource`: pipeline metadata migration/repository adapter
- `DuckDBResource`: 후속 앱이 사용할 connection factory
- asset 사이에는 파일 payload가 아니라 checksum·경로·version을 담은
  `ArtifactReference`만 전달

## Job과 sensor

- `process_collection_batch`: 현재 실행 가능
- `refresh_mfds_reference`: Stage 07 graph contract, 실행 시 명시적으로 fail-fast
- `rebuild_reconciliation`: Stage 07 graph contract, 실행 시 명시적으로 fail-fast
- `publish_gold_dataset`: Stage 10 graph contract, 실행 시 명시적으로 fail-fast
- `accepted_collection_sensor`: 새 accepted directory를 dynamic partition으로
  추가하고 Collection job을 요청하며 기본 상태는 `STOPPED`

## 로컬 실행

```bash
docker compose --profile platform up -d dagster
```

기본 UI는 `http://127.0.0.1:3000`이다. 이 UI와 metadata DB credential은
플랫폼 관리자 전용이며 Console에 노출하지 않는다.

환경변수:

- `DAGSTER_PORT` (기본 `3000`)
- `DAGSTER_MEMORY_LIMIT` (기본 `1g`)
- `PIPELINE_CODE_VERSION` (기본 `dev`, 운영 실행은 git SHA 권장)
- 기존 `DATABASE_URL`

Dagster 자체 run/event storage는 `dagster-home` Docker volume, artifact와
DuckDB 파일은 기존 `datasets` bind mount에 저장한다. 일반 종료에서는
volume을 삭제하지 않는다.

## 부분 재실행과 멱등성

관리자는 UI에서 `collection_batches`의 특정 `batch_id`와 asset subset을
선택해 재실행한다. accepted 입력은 불변이며 normalizer repository의
deterministic run/artifact key가 같은 partition 재실행의 중복을 막는다.
데이터 계약 오류는 retry 대상이 아니며 upstream 실패 시 downstream asset은
실행되지 않는다.
