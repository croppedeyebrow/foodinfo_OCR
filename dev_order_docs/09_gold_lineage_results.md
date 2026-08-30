# 9단계 — Gold 생성·계보·결과 UI

## 목표

품질검사를 통과한 최소 서비스 데이터를 versioned Gold로 생성하고 결과와 계보를 운영 UI에서 조회한다.

## Gold 필드 원칙

- external product ID
- 표준 food ID 또는 mapping key
- product name
- storage type
- expiration value/unit/basis
- selected source
- confidence
- review status
- data version

OCR 원문, PDF payload, 전체 후보, 내부 로그는 Gold에 넣지 않는다.

## Bundle

```text
datasets/gold/freshness_profiles/{dataset_version}/
├─ freshness_profiles.parquet
├─ freshness_profiles.csv
├─ manifest.json
└─ quality_summary.json
```

## 결과 UI

- Candidate·Bronze·Silver·Reconciled·Gold·Quarantine 건수
- 완전성·유일성·파싱률·매칭률·lineage 연결률
- 상품별 선택 결과와 근거
- Gold → 양쪽 Silver → Bronze → 원본 출처 계보
- 결과 bundle 다운로드

## 완료 조건

- 승인되지 않은 레코드는 Gold에 포함되지 않는다.
- manifest에 입력 checksum·계약·rule·code version과 품질 요약이 있다.
- 같은 dataset version이 중복 생성되지 않는다.
- UI에서 Gold 레코드의 전체 source lineage를 조회할 수 있다.
