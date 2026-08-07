# 데이터 계약과 저장 형식

## 계약

- collection submission
- Kurly raw product
- MFDS raw record
- normalized freshness
- reconciled freshness
- Gold freshness

모든 계약은 `schema_version`, `run_id`, `batch_id`, 출처, checksum, parser/rule version을 포함한다.

## 형식

| 데이터 | 형식 |
|---|---|
| 상품별 원문 | JSON |
| 다수 원문 | JSONL |
| Silver·Gold | Parquet |
| 사람 검토 | CSV |
| 실행·산출물 목록 | Manifest JSON |

CSV를 유일한 source of truth로 사용하지 않는다. major schema 변경은 consumer 지원 여부를 확인한 뒤 진행한다.

## 계층

- 기존 crawl/OCR 경로: Bronze 원천으로 간주
- `datasets/inbox/accepted`: 접수 완료 batch
- `datasets/silver`: 출처별 표준화
- `datasets/gold`: 배포 데이터
- `datasets/quarantine`: 검토·거절 데이터

## 구현 위치 (v1)

| 항목 | 경로 |
|---|---|
| JSON Schema | `contracts/*.schema.json` |
| Pydantic·검증 | `apps/normalizer/src/contracts.py` |
| checksum | `apps/normalizer/src/checksum.py` + `checksum_rules.md` |
| products.csv adapter | `apps/normalizer/src/adapters/products_csv.py` |

```bash
docker compose run --rm normalizer python -m src.cli list-contracts
docker compose run --rm normalizer python -m src.cli validate-contract --contract kurly_raw_product --file /tmp/record.json
docker compose run --rm normalizer python -m src.cli adapt-products-csv \
  --products /outcome/{member}/{batch}/products.csv \
  --batch-id {batch} --member {member} \
  --output /data/inbox/accepted/{batch}/collection_submission.json
```
