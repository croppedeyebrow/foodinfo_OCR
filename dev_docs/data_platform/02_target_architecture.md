# 목표 데이터 플랫폼 아키텍처

## 책임 영역

| 영역 | 책임 |
|---|---|
| Collection | 컬리 발견·수집·OCR |
| Intake | 계약 검증·배치 접수 |
| Transformation | 출처별 Silver 표준화 |
| Reconciliation | 컬리·식약처 비교·보정 |
| Quality | 승인·검토·거절 |
| Publication | Gold 생성·Backend 전달 |

## 목표 구성

```text
apps/
├─ console
├─ crawler
├─ ocr-parser
├─ normalizer
├─ mfds-parser
├─ reconciler
├─ quality
└─ publisher

orchestration/
├─ assets
├─ jobs
├─ resources
└─ definitions.py
```

Dagster는 실행과 lineage만 담당하고 변환·보정 업무 규칙은 각 Python 앱에 둔다. Collection 영역은 Platform 내부 앱을 import하지 않는다.
