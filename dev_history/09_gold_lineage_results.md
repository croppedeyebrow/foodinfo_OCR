# 9단계 — Gold 생성·계보·결과 UI

- **지시 문서**: `dev_order_docs/09_gold_lineage_results.md`
- **완료일**: 2026-08-30
- **상태**: DONE

## 결과 요약

승인된 Reconciled 레코드만 `gold_freshness` 계약으로 발행하는 **`gold_freshness_publish`** Stage와 Console **`/steps/results`**(OPERATOR 전용)를 구현했다. bundle은 `datasets/gold/freshness_profiles/{pair_id}/`에 저장되며, 같은 `dataset_version`(pair id) 중복 생성은 거부한다.

## 변경 파일과 이유

| 영역 | 주요 파일 | 이유 |
|---|---|---|
| Gold 변환 | `gold_transform/publish.py` | APPROVED reconciled → Gold Parquet/CSV |
| 계보 | `gold_transform/lineage.py` | Gold→Reconciled→Silver→Bronze→원본 chain |
| 요약 | `gold_transform/summary.py` | 레이어 건수·품질·lineage API |
| Stage | `gold_freshness_publish.py` | PipelineService 연동·중복 방지 |
| 저장 | `storage_paths.py` | `gold_freshness_profiles_dir` |
| Console | `step_results.html`, `main.py`, `base.html` | Gold 발행·요약·계보·다운로드 |
| 게이트웨이 | `pipeline_gateway.py` | summary/lineage normalizer 격리 호출 |
| 테스트 | `test_gold_publish.py` | 발행·중복거부·Stage E2E |

## 데이터 흐름

```text
reconciled/{pair_id}/records.parquet (review_status=APPROVED만)
  + kurly silver products/evidence
  + kfia silver records
  → gold/freshness_profiles/{pair_id}/
      freshness_profiles.parquet, .csv, manifest.json,
      quality_summary.json, lineage.jsonl
```

`dataset_version` = 대조 pair id (`{kurly_batch}__{kfia_dataset}`)

## Console

- `/steps/results`: 레이어 건수, Gold Publish 실행, bundle 요약, 레코드별 계보 조회
- 다운로드: `freshness_profiles.csv`, `manifest.json`
- API: `/api/results/pairs/{pair_id}/summary`, `/lineage/{gold_record_id}`

## 검증

```text
pytest tests/test_gold_publish.py tests/test_reconciliation_pipeline.py -q
```

## 잔여 과제 (10단계)

- Backend publish 계약·전달 API
- 검토 결정 반영 후 Gold selective 재발행
