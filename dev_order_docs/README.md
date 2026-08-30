# NaengLog 데이터 플랫폼 개발 디렉팅

이 폴더는 `foodinfo_OCR`의 데이터 플랫폼 개편을 위한 단일 개발 지시 문서 모음이다. 기존 `dev_docs`와 `dev_order`를 대신하며, 설계 설명과 구현 명령을 각 단계 문서에 함께 둔다.

## 확정 방향

- 기존 상품 발견·상세 수집·이미지 판별·OCR 기능을 보존한다.
- 팀원 결과는 Git으로 공유하고 운영자가 UI에서 검증·승인한다.
- Dagster는 제거한다.
- 사용자는 CLI가 아니라 Console UI에서 파이프라인을 단계적으로 실행한다.
- 업무 로직은 UI가 아닌 Python Application Service에 둔다.
- 컬리 데이터와 KFIA 소비기한 기준 데이터를 각각 Bronze·Silver로 처리한다.
- 두 Silver를 대조해 품질검토 후 Gold를 만든다.
- 실행 이력·artifact·checksum·lineage·품질 결과는 PostgreSQL에 기록한다.
- 변환은 Python 3.12, Polars, Parquet, DuckDB를 중심으로 구현한다.

## 실행 순서

| 단계 | 문서 | 초기 상태 | 결과 |
|---:|---|---|---|
| 0 | `00_execution_rules.md` | ACTIVE | 공통 작업 규칙 |
| 1 | `01_current_baseline.md` | DONE | 기존 기능 기준선 |
| 2 | `02_contracts_and_storage.md` | DONE | 계약·저장 계층 |
| 3 | `03_pipeline_metadata.md` | DONE | 실행·artifact·lineage 메타데이터 |
| 4 | `04_operator_submission_ui.md` | DONE | 전체 팀원 검증·제출 UI |
| 5 | `05_pipeline_ui_foundation.md` | DONE | UI 단계 실행 기반 |
| 6 | `06_kurly_bronze_silver.md` | DONE | 컬리 Bronze·Silver |
| 7 | `07_kfia_reference_pipeline.md` (+ `07a_kfia_native_csv_contract_adapter.md`) | DONE | KFIA Reference Bronze·Silver |
| 8 | `08_reconciliation_quality.md` | DONE | 컬리–KFIA 대조·품질검토 |
| 9 | `09_gold_lineage_results.md` | READY | Gold·계보·결과 UI |
| 10 | `10_backend_publish.md` | BLOCKED | Backend 전달 계약 |
| 11 | `11_final_integration.md` | BLOCKED | Dagster 제거·Docker·E2E |

한 번에 하나의 `READY` 또는 `IN_PROGRESS` 단계만 수행한다. 선행 단계가 완료되기 전에 후속 단계를 구현하지 않는다.

## 개발 내역

완료된 단계의 구현 결과·테스트·잔여 과제는 [`dev_history/`](../dev_history/README.md)에 단계별로 기록한다.

- `dev_order_docs/` — 무엇을 만들지 (지시)
- `dev_history/` — 무엇을 만들었는지 (내역)

## 목표 사용자 흐름

```text
컬리: 발견 → 상세수집 → 이미지판별 → OCR → 검증·제출 → Bronze → Silver
KFIA: 기준파일 등록 → 계약검증 → Reference Bronze → Reference Silver
통합: 컬리–KFIA 대조 → 품질검토 → Gold → 결과·계보 조회
```

## AI 실행 프롬프트

```text
AGENTS.md와 dev_order_docs/README.md를 읽고,
dev_order_docs/00_execution_rules.md와 현재 READY 단계 문서를 끝까지 읽어.
현재 단계 범위만 구현하고, 지정된 검증을 수행한 뒤 완료 보고 형식으로 보고해.
```
