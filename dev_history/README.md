# NaengLog 데이터 플랫폼 — 개발 내역

이 폴더는 **완료된 구현 결과**를 단계별로 기록한다.

| 구분 | 폴더 | 역할 |
|---|---|---|
| 지시·설계 | [`dev_order_docs/`](../dev_order_docs/README.md) | 무엇을, 어떤 순서로, 어떤 조건으로 만들지 |
| 개발 내역 | `dev_history/` (여기) | 실제로 무엇을 만들었는지, 검증 결과, 잔여 과제 |

## 기록 규칙

- 한 단계가 `dev_order_docs/README.md`에서 **DONE**이 되면, 같은 번호의 내역 문서를 추가·갱신한다.
- 각 내역 문서는 [`dev_order_docs/00_execution_rules.md`](../dev_order_docs/00_execution_rules.md)의 **완료 보고** 형식을 따른다.
- 지시 문서와 충돌하면 **지시 문서가 우선**이며, 내역 문서에 차이를 명시한다.
- Dagster 관련 코드는 **11단계까지 레거시로 남을 수 있음**을 내역에 구분해 적는다.

## 단계별 상태

| 단계 | 지시 문서 | 내역 문서 | 상태 |
|---:|---|---|---|
| 0 | `00_execution_rules.md` | — | 규칙만 존재 (내역 생략) |
| 1 | `01_current_baseline.md` | [`01_current_baseline.md`](01_current_baseline.md) | DONE |
| 2 | `02_contracts_and_storage.md` | [`02_contracts_and_storage.md`](02_contracts_and_storage.md) | DONE |
| 3 | `03_pipeline_metadata.md` | [`03_pipeline_metadata.md`](03_pipeline_metadata.md) | DONE |
| 4 | `04_operator_submission_ui.md` | [`04_operator_submission_ui.md`](04_operator_submission_ui.md) | DONE |
| 5 | `05_pipeline_ui_foundation.md` | [`05_pipeline_ui_foundation.md`](05_pipeline_ui_foundation.md) | DONE |
| 6 | `06_kurly_bronze_silver.md` | [`06_kurly_bronze_silver.md`](06_kurly_bronze_silver.md) | DONE |
| 7 | `07_kfia_reference_pipeline.md` | — | READY |
| 8 | `08_reconciliation_quality.md` | — | BLOCKED |
| 9 | `09_gold_lineage_results.md` | — | BLOCKED |
| 10 | `10_backend_publish.md` | — | BLOCKED |
| 11 | `11_final_integration.md` | — | BLOCKED |

## 다음 작업

현재 **7단계** [`07_kfia_reference_pipeline.md`](../dev_order_docs/07_kfia_reference_pipeline.md) — KFIA Reference Bronze·Silver.

새 단계 완료 시 [`_template.md`](_template.md)를 복사해 번호에 맞는 파일을 작성한다.
