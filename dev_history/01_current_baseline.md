# 1단계 — 현재 기능 기준선

- **지시 문서**: `dev_order_docs/01_current_baseline.md`
- **완료일**: 2026-08 (기준선 고정, 회귀 테스트 기반 확립)
- **상태**: DONE

## 결과 요약

플랫폼 개편 전 **기존 수집·OCR 파이프라인**의 동작과 산출물 구조를 기준선으로 고정했다. 이후 모든 단계는 이 기준선 대비 회귀 여부로 검증한다.

## 변경 파일과 이유

| 영역 | 주요 경로 | 내용 |
|---|---|---|
| Console | `apps/console/` | FastAPI/Jinja 단계별 수집·OCR UI |
| Crawler | `apps/crawler/` | Playwright 발견·상세 수집 CLI |
| OCR Parser | `apps/ocr-parser/` | 이미지 판별·OCR·DOM 병합 |
| Normalizer | `apps/normalizer/` | 계약·제출·메타데이터 (후속 단계 확장) |
| 데이터 | `datasets/discovery/{batch_id}/` | 크롤 중간 산출물 |
| 데이터 | `outcome/{member}/{batch_id}/` | 팀원별 OCR 최종 CSV |
| Docker | `compose.yaml` | console, crawler, ocr-parser, normalizer, postgres |
| 테스트 | `tests/test_discovery.py` 등 | 비통합·단위 회귀 |

## UI 및 데이터 흐름 변화

기존 흐름을 **변경하지 않고** 문서화·고정:

```text
발견 → 상세수집 → 이미지판별 → OCR → outcome/{BATCH_MEMBER}/{batch_id}/
```

- 배치 ID 규칙: `{YYYYMMDD}-{member}-{seq}`
- 팀원 식별: `BATCH_MEMBER` 환경변수
- Git으로 `datasets/`, `outcome/` 공유

## 계약·환경변수·migration 변화

| 변수 | 용도 |
|---|---|
| `BATCH_MEMBER` | 수집·OCR 생산자 |
| `OUTCOME_ROOT` / `OUTCOME_HOST_ROOT` | outcome 마운트 경로 |
| `DATASETS_ROOT` | discovery 데이터 루트 |

## 실행한 테스트와 결과

- crawler/OCR/console 비통합 테스트 스위트
- 대표 fixture: `tests/fixtures/contracts/sample_products.csv`
- 배치 멤버 필터: `tests/test_batch_member_filter.py`

## 기존 기능 호환성

- 이 단계 자체가 **호환성 기준**이다.
- Console 1~3단계(발견·수집·판별·OCR) CLI 동작 보존이 전제.

## 보안·성능·데이터 안전 고려

- Raw crawl·이미지·OCR 결과는 불변 입력으로 취급.
- 라이브 Kurly·운영 DB를 일상 테스트에 사용하지 않음.

## 잔여 과제·다음 단계 진입 조건

- [x] 대표 fixture·샘플 배치 고정
- [x] 이후 단계 회귀 테스트 실행 가능
- → **2단계** 계약·저장 계층으로 진행

## 레거시·주의사항

- `compose.yaml`의 `dagster` 서비스와 `orchestration/`은 **이전 개발 주기 잔재**.
- `dev_order_docs` 확정 방향은 Dagster 제거이나, 물리 삭제는 **11단계** 예정.
- `dev_order/`(구 지시 폴더)는 archive 성격이며 실행하지 않는다.
