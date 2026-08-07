# 5단계 — Dagster Asset 오케스트레이션

## 목표

기존 Python 앱을 재작성하지 않고 asset으로 감싸 의존관계, 부분 재실행, 계보를 제공한다.

## Asset 그래프

```text
kurly_collection_submission
  → kurly_bronze_validated
  → kurly_silver_freshness ─┐
                            ├→ reconciled_freshness
mfds_source_pdf             │
  → mfds_bronze_records     │
  → mfds_silver_freshness ──┘

reconciled_freshness
  → freshness_quality_checked
  → gold_freshness_profiles
  → backend_export_bundle
```

## Asset 설계 원칙

- asset은 파일 내용을 메모리로 전달하기보다 artifact reference를 반환한다.
- 실제 변환 코드는 각 앱의 순수 함수 또는 public CLI에 둔다.
- Dagster 정의 파일에 업무 규칙을 넣지 않는다.
- partition key는 우선 `batch_id`, Gold는 dataset version을 사용한다.
- 재시도는 외부 I/O 단계에 제한하며 데이터 오류는 무한 재시도하지 않는다.
- 팀원은 Dagster UI를 사용하지 않는다.

## Resource

- filesystem/artifact store
- pipeline metadata DB
- DuckDB connection factory
- configuration/secrets
- OCR collection은 외부 제출 asset으로 취급

## Job

- `process_collection_batch`
- `refresh_mfds_reference`
- `rebuild_reconciliation`
- `publish_gold_dataset`

## 테스트

- asset unit test
- temp directory 기반 resource
- 한 asset 실패 후 downstream 미실행
- 같은 partition 재실행 idempotency
- materialization metadata 검증

## 완료 조건

- accepted batch부터 Gold 전 단계까지 그래프가 보인다.
- 특정 batch와 asset만 재실행할 수 있다.
- 기존 Console 없이도 fixture로 pipeline test가 가능하다.

## AI 지시문

```text
기존 앱 코드를 Dagster 안으로 복사하지 말고 public function/CLI를 호출하는 얇은 asset을 작성해.
batch_id partition과 artifact reference를 사용하고 실제 컬리/OCR 작업은 외부 제출 asset으로 취급해.
```
