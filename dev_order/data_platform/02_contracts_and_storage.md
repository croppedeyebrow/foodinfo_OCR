# 2단계 — 데이터 계약과 저장 계층

## 목표

독립 실행되는 수집·PDF·정제 프로그램을 versioned contract와 manifest로 연결한다.

## 기존 경로 호환 정책

초기에는 기존 경로를 Bronze 원천으로 간주한다.

| 개념 계층 | 기존/신규 경로 |
|---|---|
| Discovery | `datasets/discovery/{batch_id}` |
| Bronze crawl | `datasets/crawl_raw` |
| Bronze images | `datasets/detail_images` |
| Bronze OCR | `datasets/ocr_raw` |
| Collection output | `outcome/{member}/{batch_id}` |
| Accepted inbox | `datasets/inbox/accepted/{batch_id}` |
| Silver | `datasets/silver/{source}/{batch_id}` |
| Gold | `datasets/gold/{dataset}/{version}` |
| Quarantine | `datasets/quarantine/{batch_id}` |
| Manifest | 각 batch 디렉터리의 `manifest.json` |

## 계약 파일

```text
contracts/
├─ collection_submission.schema.json
├─ kurly_raw_product.schema.json
├─ mfds_raw_record.schema.json
├─ normalized_freshness.schema.json
├─ reconciled_freshness.schema.json
└─ gold_freshness.schema.json
```

## 공통 메타 필드

- `schema_version`
- `run_id`
- `batch_id`
- `record_id`
- `source`
- `source_record_id`
- `source_uri`
- `content_hash`
- `parser_version`
- `created_at`

## 저장 형식

- 상품별 원문: JSON
- 다수 원문 스트림: JSONL
- Silver/Gold: Parquet
- 사람이 검토하는 파일: CSV
- 실행 및 파일 목록: Manifest JSON

CSV는 파이프라인의 유일한 source of truth로 사용하지 않는다.

## 계약 버전 규칙

- backward compatible 필드 추가: minor 증가
- 필드 삭제·타입 변경·의미 변경: major 증가
- producer와 consumer가 지원하는 version을 명시
- unknown major version은 즉시 거부

## 구현 작업

1. JSON Schema와 대응 Pydantic model을 작성한다.
2. 샘플 valid/invalid fixture를 만든다.
3. 계약 validation CLI를 제공한다.
4. checksum 계산 범위와 정렬 방식을 문서화한다.
5. 기존 `products.csv`를 신규 contract로 읽는 compatibility adapter를 작성한다.

## 완료 조건

- 같은 입력은 같은 checksum을 만든다.
- invalid fixture가 명확한 경로와 오류코드로 실패한다.
- 기존 OCR 결과를 이동하지 않고 신규 제출 계약으로 변환할 수 있다.

## AI 지시문

```text
기존 products.csv와 원문 JSON을 보존하면서 versioned JSON Schema, Pydantic model,
validation CLI, fixtures를 구현해. 기존 컬럼을 추측해 제거하지 말고 compatibility adapter로 연결해.
```
