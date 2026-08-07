# NaengLog 데이터 플랫폼 개요

## 목적

기존 컬리 상품 발견·상세 수집·OCR UI를 보존하면서, 식약처 PDF 참조 데이터와 교차 정제하여 검증된 Gold 데이터를 Backend에 전달한다.

## 사용자 경계

- 팀원: Console UI에서 발견 → 상세 → 이미지 판별 → OCR → 배치 제출
- 재성: 계약, Dagster, Polars, 식약처 결합, 품질검사, Gold 배포 구축 및 운영

## 기술 방향

- Python 3.12 중심
- Dagster orchestration
- Polars + DuckDB + Parquet
- PostgreSQL pipeline metadata
- Rust는 benchmark gate 통과 시에만 선택 도입
- Go, Spark, Kafka, Airflow, Kubernetes는 현재 제외

## 데이터 흐름

```text
Console/Crawler/OCR
→ Accepted Collection Batch
→ Kurly Silver
                   ┐
MFDS PDF → MFDS Silver
                   ├→ Reconciliation → Quality → Gold → Backend
                   ┘
```

## 문서 구분

- `dev_docs`: 설계·계약·운영 참고문서
- `dev_order`: AI가 순서대로 실행할 구현 지시서
- `archive`: 완료된 과거 자료
