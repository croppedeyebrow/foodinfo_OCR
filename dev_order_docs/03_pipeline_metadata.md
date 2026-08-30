# 3단계 — 실행 이력·Artifact·Lineage

## 목적

Dagster 없이 UI에서 실행되는 각 Stage의 상태·재실행·산출물·계보를 PostgreSQL에 기록한다.

## 유지할 테이블

| 테이블 | 역할 |
|---|---|
| `pipeline_runs` | 배치 또는 dataset 실행 |
| `pipeline_steps` | Stage별 attempt·상태·시간·건수 |
| `pipeline_artifacts` | 경로·형식·계약·checksum·크기 |
| `pipeline_artifact_lineage` | parent artifact → child artifact |
| `quality_results` | rule별 품질 결과 |
| `schema_migrations` | metadata schema migration |

## 멱등키

```text
stage + input_checksum + contract_version + code_version + rule_version
```

## 상태

```text
PENDING → RUNNING → SUCCEEDED
                  ↘ FAILED
                  ↘ REVIEW_REQUIRED
```

## 변경 지침

- 기존 metadata repository와 migration을 재사용한다.
- `dagster_adapter.py`는 최종 통합 단계까지 호환용으로 남길 수 있으나 새 코드에서 사용하지 않는다.
- `PipelineService`가 run·step·artifact 기록을 호출한다.
- DB에 원본 파일 payload를 넣지 않는다.

## 완료 조건

- UI에서 run ID로 상태와 오류를 조회할 수 있다.
- Gold에서 원본 컬리 배치와 KFIA dataset version까지 역추적할 수 있다.
- 같은 멱등키의 중복 artifact가 생성되지 않는다.
