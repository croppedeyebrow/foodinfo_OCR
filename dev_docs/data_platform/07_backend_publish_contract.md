# Gold와 Backend 배포 계약

## Backend 전달 데이터

- external product ID
- food mapping key
- product name
- storage type
- expiration value/unit/basis
- selected source
- confidence
- review status
- dataset version

원문 OCR/PDF, 전체 후보, 디버그 로그는 전달하지 않는다.

## 공식 bundle

```text
freshness_profiles.parquet
freshness_profiles.csv
manifest.json
quality_summary.json
```

Backend는 manifest/schema/checksum을 검증하고 dataset version 단위로 idempotent upsert한다.
