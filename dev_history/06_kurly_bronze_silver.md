# 6단계 — 컬리 Bronze·Silver UI

- **지시 문서**: `dev_order_docs/06_kurly_bronze_silver.md`
- **완료일**: 2026-08-30
- **상태**: DONE

## 결과 요약

accepted 배치를 **Kurly Bronze**(계약 검증·evidence 보존·Parquet)와 **Kurly Silver**(Polars 중복 통합·enum 표준화·evidence JSONL)로 변환하는 Stage를 구현하고 Console `/steps/pipeline`에서 실행·요약·근거 조회가 가능하다.

## 변경 파일과 이유

| 영역 | 주요 파일 | 이유 |
|---|---|---|
| 변환 로직 | `apps/normalizer/src/kurly_transform/bronze.py` | accepted → bronze Parquet·manifest·quarantine |
| 변환 로직 | `apps/normalizer/src/kurly_transform/silver.py` | bronze → silver Parquet·evidence·review CSV |
| 텍스트 규칙 | `apps/normalizer/src/kurly_transform/text.py` | HTML/공백 정리·storage enum·보수적 expiration 파싱 |
| Stage | `normalizer_pipeline/stages/kurly_bronze.py`, `kurly_silver.py` | PipelineService 연동 |
| Stage 등록 | `normalizer_pipeline/stages/__init__.py` | `STAGE_REGISTRY`에 kurly bronze/silver |
| 저장 경로 | `apps/normalizer/src/storage_paths.py` | `bronze_batch_dir`, `quarantine_run_dir` |
| Console | `main.py`, `step_pipeline.html`, `step_pipeline_evidence.html` | Bronze/Silver 요약·근거 보기·review CSV |
| 의존성 | `apps/normalizer/requirements.txt` | Polars 추가 |
| 테스트 | `tests/test_kurly_bronze_silver.py` | E2E·중복 통합·결정성·실패 격리 |

## UI 및 데이터 흐름 변화

```text
accepted manifest
  → [Kurly Bronze] → datasets/bronze/kurly/{batch_id}/products.parquet + manifest.json
                  ↘ quarantine/{run_id}/bronze_records.jsonl (계약 오류)
  → [Kurly Silver] → datasets/silver/kurly/{batch_id}/products.parquet
                  → evidence.jsonl (DOM/OCR 후보·선택 근거)
                  → review.csv (검토 view)
```

Console `/steps/pipeline`:
- **Kurly Bronze / Kurly Silver** 실행 버튼
- Bronze/Silver manifest 기반 요약 카드
- **상품 근거 보기** (`/steps/pipeline/evidence/{batch_id}`)
- **검토 CSV** 다운로드

## 계약·환경변수·migration 변화

- 입력: `collection_submission` (accepted)
- Bronze 출력: `kurly_raw_product` (Parquet 행)
- Silver 출력: `normalized_freshness` (Parquet 행)
- evidence는 계약 외 `evidence.jsonl`에 보존 (`REVIEW_REQUIRED` 포함)
- Silver rule version: `kurly_silver_v1.0.0`
- DB migration 없음

## 실행한 테스트와 결과

```text
pytest tests/test_kurly_bronze_silver.py tests/test_console.py -q
# 43 passed

pytest -q
# 129 passed, 2 skipped (psycopg integration 2건 — 환경 이슈)
```

## 운영 검증 (2026-08-30)

- Docker Console + `.env` OPERATOR 설정으로 **41개 배치** 일괄 검증·accepted 제출
- `/steps/pipeline`에서 **Kurly Bronze → Kurly Silver** 실행·요약·근거 화면 확인 (사용자 검증 완료)
- 계약 미충족 배치 `20260724-jaeseong-001` (`image_text_check.csv` 없음) — discovery·outcome 삭제로 제외

## 기존 기능 호환성

- 수집·OCR·검증·제출(1~5단계) 변경 없음
- `fixture_echo` Stage는 registry에 유지하되 Console UI에서는 숨김
- immutable raw/outcome 입력 미변경, staging 후 승격

## 보안·성능·데이터 안전 고려

- OPERATOR 전용 pipeline API/UI (4~5단계와 동일)
- Silver 실패 시 기존 성공 산출물 미훼손 (staging → promote)
- quarantine 레코드는 삭제하지 않고 JSONL 보존
- 도메인 임계값·OCR 보정값 임의 생성 없음 — 불확실 값은 `REVIEW_REQUIRED`

## 잔여 과제·다음 단계 진입 조건

- **7단계** KFIA Reference Bronze·Silver
- expiration 파싱 규칙은 보수적 v1 — 도메인 확정 시 rule version bump
- PostgreSQL metadata에 artifact 등록은 Stage 실행 시 자동 (InMemory/DB)

## 레거시·주의사항

- Dagster `kurly_bronze_validated` asset은 metadata 등록만 수행 — 실제 변환은 Console Pipeline이 담당
- `normalized_freshness` 스키마에 evidence 필드 없음 → `evidence.jsonl` 분리 저장
- 5단계 운영 핫픽스(`pipeline_gateway`, postgres `depends_on`) — [`05_pipeline_ui_foundation.md`](05_pipeline_ui_foundation.md) 참고
