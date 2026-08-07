# 10단계 — Gold 데이터와 Backend 배포 계약

## 목표

품질검사를 통과한 최소 서비스 데이터만 versioned Gold로 만들고 Backend가 idempotent하게 가져가도록 한다.

## Gold 필드 원칙

Backend 운영에 필요한 값만 포함한다.

- external product ID
- 표준 food 식별자 또는 매핑 key
- product name
- storage type
- expiration value/unit/basis
- selected source
- confidence
- review status
- data version

원문 OCR JSON, PDF 원문, 후보 전체, 내부 디버그 로그는 포함하지 않는다.

## Gold bundle

```text
datasets/gold/freshness_profiles/{dataset_version}/
├─ freshness_profiles.parquet
├─ freshness_profiles.csv
├─ manifest.json
└─ quality_summary.json
```

CSV는 확인·호환용이며 Parquet과 manifest가 공식 배포 산출물이다.

## Manifest

- dataset name/version
- schema version
- rule version
- input artifact IDs/checksums
- row count
- quality summary
- output checksums
- created_at

## Backend 연계

초기에는 파일 bundle import를 사용한다. 향후 API가 필요하면 별도 ADR로 결정한다.

Backend import는 다음을 수행한다.

1. manifest/schema/checksum 검증
2. dataset version 중복 확인
3. transaction 단위 staging
4. 도메인 Service를 통한 upsert
5. publish 결과 기록

## 완료 조건

- 같은 dataset version의 중복 적재가 발생하지 않는다.
- 실패 시 부분 적재가 남지 않는다.
- Gold에서 Bronze 입력과 rule version까지 추적 가능하다.

## AI 지시문

```text
승인된 record만 Gold bundle로 생성하고 manifest/checksum을 포함해.
Backend 내부 모델을 pipeline에 import하지 말고 versioned contract로 연결해.
중간 OCR/PDF payload는 Gold와 Backend DB에서 제외해.
```
