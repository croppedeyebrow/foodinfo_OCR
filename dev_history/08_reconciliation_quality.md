# 8단계 — Kurly–KFIA 대조·품질검토

- **지시 문서**: `dev_order_docs/08_reconciliation_quality.md`
- **완료일**: 2026-08-30
- **상태**: DONE

## 결과 요약

Kurly Silver(`products.parquet`)와 KFIA Reference Silver(`records.parquet`)를 pair 단위로 대조하는 **`kurly_kfia_reconcile`** Stage와 Console **`/steps/reconciliation`**(OPERATOR 전용)을 구현했다. 매칭은 승인된 rule 문서 없이 임의 임계값을 두지 않고, **관리 매핑 → exact food_type + storage 호환 → expiration 일치** 순의 보수적 규칙(`kurly_kfia_reconcile_v1.0.0`)만 적용한다. 불확실·미기준 건은 `REVIEW_REQUIRED`로 남기며 자동 승인하지 않는다.

## 변경 파일과 이유

| 영역 | 주요 파일 | 이유 |
|---|---|---|
| 매칭 | `reconciliation/matching.py` | RECONCILE-001~005 규칙·ROOM↔AMBIENT 호환 |
| 실행 | `reconciliation/run.py` | Parquet·evidence·review.csv·manifest·decisions.jsonl |
| Stage | `kurly_kfia_reconcile.py` | PipelineService 연동 |
| 저장 | `storage_paths.py` | `reconciled/{pair_id}`·`reconciled/mappings` |
| 계약 | `review_decision.schema.json` | 수동 검토 결정 audit |
| Console | `step_reconciliation.html`, `main.py`, `auth.py`, `base.html` | pair 선택·대조 실행·요약·검토 CSV |
| 게이트웨이 | `pipeline_gateway.py` | 검토 결정 append API |
| 테스트 | `test_reconciliation_matching.py`, `test_reconciliation_pipeline.py` | 규칙 단위·E2E |

## 데이터 흐름

```text
silver/kurly/{batch}/products.parquet
  +
silver/kfia/{dataset}/records.parquet
  → [kurly_kfia_reconcile] datasets/reconciled/{kurly_batch}__{kfia_dataset}/
      records.parquet, evidence.jsonl, review.csv, manifest.json
      decisions.jsonl (수동 검토 결정 append)
```

pair id 형식: `{kurly_batch_id}__{kfia_dataset_version}`

## 매칭 규칙 (v1.0.0)

| rule_id | 조건 | review_status | match_type |
|---|---|---|---|
| RECONCILE-001 | `datasets/reconciled/mappings/default.json` 관리 매핑 | APPROVED | MANAGED_MAPPING |
| RECONCILE-002 | `food_name_normalized` = `food_type` exact + storage 호환 + expiration(일) 일치 + 후보 1건 | APPROVED | EXACT_NAME_UNIQUE |
| RECONCILE-003 | exact name·storage 일치 후보 2건 이상 | REVIEW_REQUIRED | MULTI_CANDIDATE |
| RECONCILE-004 | exact name·storage 일치, expiration 불일치 | REVIEW_REQUIRED | EXACT_NAME_EXPIRATION_MISMATCH |
| RECONCILE-005 | 기준 미매칭 | REVIEW_REQUIRED | NO_REFERENCE |

`REJECTED` 상태는 v1에서 자동 생성하지 않는다(수동 결정 API만 기록).

## Console

- `/steps/reconciliation`: Kurly Silver 배치 + KFIA dataset 선택 → 대조 실행 → 승인·검토·미기준 건수·검토 CSV
- `POST /api/reconciliation/decisions`: 검토자·시각·사유·action 기록
- 팀원 Console(`COLLECTOR`)에는 노출하지 않음 (`is_operator` nav)

## 검증

```text
pytest tests/test_reconciliation_matching.py tests/test_reconciliation_pipeline.py -q
→ 10 passed
```

## 잔여 과제 (9단계 이후)

- 검토 결정 후 reconciled 레코드 **선택적 재처리**(현재는 `decisions.jsonl` audit만)
- fuzzy·category 후보 매칭은 승인 rule 문서 확정 후 추가
- Gold publish·lineage UI (9단계)
