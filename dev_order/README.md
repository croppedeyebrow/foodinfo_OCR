# 데이터 플랫폼 개발 실행 순서

## 사용법

AI는 한 번에 하나의 `READY` 또는 `IN_PROGRESS` 단계만 수행한다. 완료 후 사용자가 결과를 검토하고 다음 단계의 상태를 변경한다.

## 상태 정의

- `READY`: 다음 실행 대상
- `IN_PROGRESS`: 현재 구현 중
- `DONE`: 구현·검증 완료
- `BLOCKED`: 선행 단계 또는 결정 대기
- `SKIPPED`: 검토 결과 생략
- `SUPERSEDED`: 다른 문서로 대체

## 진행표

| 순서 | 문서 | 상태 | 주요 결과 |
|---:|---|---|---|
| 0 | `data_platform/00_execution_rules.md` | ACTIVE | 모든 단계의 AI 작업 규칙 |
| 1 | `data_platform/01_repository_baseline.md` | DONE | 현재 기능과 테스트 기준선 (`current_baseline.md`) |
| 2 | `data_platform/02_contracts_and_storage.md` | DONE | 계약·Manifest·저장 계층 |
| 3 | `data_platform/03_console_submission.md` | BLOCKED | 팀원 UI 배치 제출 |
| 4 | `data_platform/04_pipeline_metadata.md` | BLOCKED | 실행 이력과 lineage |
| 5 | `data_platform/05_dagster_orchestration.md` | BLOCKED | Dagster asset 그래프 |
| 6 | `data_platform/06_polars_transformation.md` | BLOCKED | Silver 표준화 |
| 7 | `data_platform/07_mfds_reconciliation.md` | BLOCKED | 식약처 결합·교차 보정 |
| 8 | `data_platform/08_quality_review.md` | BLOCKED | 품질 게이트·검토 |
| 9 | `data_platform/09_rust_benchmark_gate.md` | BLOCKED | Rust 도입 판단 |
| 10 | `data_platform/10_gold_backend_publish.md` | BLOCKED | Gold·Backend 계약 |
| 11 | `data_platform/11_final_integration.md` | BLOCKED | Docker·E2E·점진 전환 |

## 실행 프롬프트

```text
AGENTS.md와 dev_order/README.md를 먼저 읽어.
그다음 dev_order/data_platform/00_execution_rules.md와 현재 READY 단계 문서를 끝까지 읽어.
현재 단계 범위만 수행하고 완료 보고 형식으로 결과를 제출해.
```

## Archive

`dev_order/archive`는 이미 구현이 끝난 과거 지시서다. 현재 명령으로 실행하지 않는다.
