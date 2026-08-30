# 1단계 — 현재 기능 기준선

## 목적

플랫폼 개편 전 기존 수집 기능과 결과 구조를 고정해 회귀 여부를 판별한다. 이 단계는 이미 완료된 것으로 취급하되, 구현 전 실제 코드와 차이가 있으면 문서를 갱신한다.

## 보존 대상

- Console 기반 상품 발견, 상세 수집, 이미지 판별, OCR
- 팀원별 `BATCH_MEMBER`
- `datasets/discovery/{batch_id}`
- `outcome/{member}/{batch_id}/products.csv`
- `outcome/{member}/{batch_id}/failures.csv`
- 기존 batch ID 규칙과 Git 공유 방식
- accepted 제출의 checksum·원자성·중복 방지

## 현재 서비스

| 서비스 | 책임 |
|---|---|
| `console` | FastAPI/Jinja 운영 UI |
| `crawler` | Playwright 발견·상세 수집 |
| `ocr-parser` | 이미지 분류·OCR·DOM 병합 |
| `normalizer` | 계약·제출·메타데이터 및 향후 Stage Service |
| `postgres` | 파이프라인 메타데이터 |
| `dagster` | 제거 예정인 기존 선택 서비스 |

## 완료 조건

- 기존 비통합 테스트 결과가 기록돼 있다.
- 대표 fixture와 샘플 배치가 고정돼 있다.
- 이후 모든 단계에서 기존 Console 수집 회귀 테스트를 실행할 수 있다.
