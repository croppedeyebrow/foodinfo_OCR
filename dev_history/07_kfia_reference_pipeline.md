# 7단계 — KFIA Reference 등록·Bronze·Silver UI

- **지시 문서**: `dev_order_docs/07_kfia_reference_pipeline.md`, `dev_order_docs/07a_kfia_native_csv_contract_adapter.md`
- **완료일**: 2026-08-30
- **상태**: DONE

## 결과 요약

`ref_data_parser`의 실제 `shelf_life_output.csv`(native 16컬럼, 963행)를 Console `/steps/reference`에서 등록·검증하고, **Reference Bronze**·**Reference Silver** Stage까지 실행한다. 초기 구현 후 **07a**에서 실제 export 형식에 맞게 Native Input Contract·Adapter·품질 규칙·Bronze/Silver 계약을 분리·수정했다. 운영 검증(`KFIA-2026-08`): Bronze 963/963, Silver 승인 874·검토 89·거절 0. 5단계 테스트용 `fixture_echo` Stage는 제거했다.

## 변경 파일과 이유

| 영역 | 주요 파일 | 이유 |
|---|---|---|
| 등록 | `reference_registration.py`, `kfia_export_columns.py` | native export 검증·manifest·checksum 중복 방지 |
| Adapter | `adapters/kfia_native_csv.py` | native row → Bronze 레코드 (`food_name` 생성 금지) |
| 품질 | `quality/kfia_rules.py` | KFIA-001~008 (안전계수·PDF 분류 불일치 등) |
| 변환 | `kfia_transform/bronze.py`, `silver.py` | Bronze/Silver Parquet·evidence·review.csv |
| Stage | `kfia_reference_bronze.py`, `kfia_reference_silver.py` | PipelineService 연동 |
| Console 게이트웨이 | `pipeline_gateway.py` | normalizer `src` 격리 import·등록/검증 API |
| Stage 정리 | `stages/__init__.py`, `fixture_echo.py` 삭제 | 운영 Stage만 registry |
| 저장 | `storage_paths.py` | `reference/inbox/{dataset_version}` |
| 계약 | `kfia_native_export`, `kfia_reference_bronze`, `kfia_reference_silver`, `kfia_reference_manifest` | 입력·Bronze·Silver·등록 manifest 분리 |
| Console | `main.py`, `step_reference.html`, `auth.py`, `base.html` | 등록·검증·Stage 실행 UI/API |
| Pipeline | `normalizer_pipeline/service.py` | Stage prefix 필터 (`kurly_` / `kfia_`) |
| 테스트 | `test_kfia_native_adapter.py`, `test_kfia_reference.py`, `test_console.py` | native adapter·E2E·Console API |
| 픽스처 | `tests/fixtures/kfia/shelf_life_output.native.sample.csv` | 실제 export 형식 샘플 |

## UI 및 데이터 흐름 변화

```text
shelf_life_output.csv (ref_data_parser native 16컬럼)
  → [등록] datasets/reference/inbox/{dataset_version}/
  → [계약 검증] Native Input Contract (food_name/raw_text 불필요)
  → [Reference Bronze] datasets/bronze/kfia/{dataset_version}/records.parquet
                    ↘ quarantine (adapter/계약 실패 행만)
  → [Reference Silver] datasets/silver/kfia/{dataset_version}/records.parquet
                    → evidence.jsonl, review.csv
```

Console `/steps/reference` (OPERATOR 전용):
- dataset version + CSV 업로드 → **등록** / **계약 검증**
- **Reference Bronze** / **Reference Silver** 실행
- manifest·Bronze/Silver 요약·Stage run 상태(HTMX 폴링)
- `parser_version`은 UI 입력 없이 `PIPELINE_CODE_VERSION`(없으면 `unknown`) 자동 기록

`/steps/pipeline`은 `kurly_*` Stage만 표시한다.

## 07a Native CSV 핵심

| 항목 | 처리 |
|---|---|
| `식품유형` | `food_type`으로 저장, `food_name`으로 대체하지 않음 |
| `source_page` | 공식 페이지 필드 |
| `raw_text` | 필수 아님 (검증 요약: "미제공 · 선택 필드") |
| `보관방법` | Silver에서 `REFRIGERATED`/`FROZEN`/`AMBIENT`/`UNKNOWN` |
| 안전계수 > 1 | `REVIEW_REQUIRED` (자동 수정 없음) |
| 품목코드·PDF 분류 불일치 | `REVIEW_REQUIRED` |

## 계약·환경변수·migration 변화

- Native 입력 검증: `kfia_native_export`
- Bronze 출력: `kfia_reference_bronze` (`source=KFIA`, `raw_payload`에 원본 16필드)
- Silver 출력: `kfia_reference_silver` (`review_status`: `APPROVED` / `REVIEW_REQUIRED` / `REJECTED`)
- 품질 rule version: `kfia_quality_v1.0.0`, Silver rule version: `kfia_silver_v1.0.0`
- KFIA pipeline `batch_id` = `dataset_version` (예: `KFIA-2026-08`)
- `CONSOLE_OPERATOR`로 reference Stage member 결정
- DB migration 없음

## 운영 검증 (2026-08-30)

| 항목 | 결과 |
|---|---|
| dataset | `KFIA-2026-08` |
| 등록 | VALIDATED · 963행 |
| Reference Bronze | 963 입력 / 963 정상 / 0 격리 |
| Reference Silver | 963 레코드 · 승인 874 · 검토 89 · 거절 0 |

검토 89건은 주로 안전계수 1 초과(파서 추출 이상값 의심). Stage는 품질 검토 건수와 무관하게 `SUCCEEDED`로 기록한다.

## 실행한 테스트와 결과

```text
pytest tests/test_kfia_native_adapter.py tests/test_kfia_reference.py \
  tests/test_kurly_bronze_silver.py tests/test_console.py -q
```

## 기존 기능 호환성

- Kurly `/steps/pipeline`·제출·수집 흐름 유지 (`normalized_freshness` / `kurly_*` 계약 영향 없음)
- Pipeline API 재사용; `kfia_*` Stage는 `resolve_operator_dataset` 사용
- `fixture_echo` 제거 — `kurly_bronze` 기준 pipeline 테스트로 대체

## 보안·성능·데이터 안전 고려

- 동일 dataset version + 동일 export checksum → idempotent 등록
- 다른 checksum 동일 version → `409 DATASET_VERSION_CONFLICT`
- Bronze/Silver에서 행 silent drop 없음 (격리·`review_status`로 명시)
- Console·normalizer `src` 패키지명 충돌 시 `run_with_normalizer_import`로 격리

## 잔여 과제·다음 단계 진입 조건

- **8단계**: 컬리 Silver ↔ KFIA Reference Silver 대조·품질검토
- **파서 측**: 안전계수 이상값(11.0, 16.0 등) 원천 수정은 `ref_data_parser` 저장소에서 별도 검토
- Dagster 물리 제거는 11단계

## 레거시·주의사항

- `ref_data_parser` 코드/PDF는 이 repo에 복사하지 않음 — `shelf_life_output.csv` export 경계만 연동
- 초기 7단계 초안은 `mfds_raw_record`/`normalized_freshness`를 KFIA에 직접 매핑했으나, 07a에서 KFIA 전용 Bronze/Silver 계약으로 대체
- `orchestration/`·compose dagster는 아직 잔존 (11단계 제거 예정)

## 운영 핫픽스 (7단계 내 기록)

| 증상 | 원인 | 조치 |
|---|---|---|
| 등록/검증 `No module named 'pipeline_gateway'` | validate API 상대 import 누락 | `from .pipeline_gateway` 수정 |
| 등록 시 Internal Server Error | console `src`와 normalizer `src` 충돌 | `run_with_normalizer_import`·게이트웨이 래퍼 |
| Silver `FAILED` (out=963, fail=89) | 품질 검토 건수를 `failed_count`로 전달 | `kfia_reference_silver` Stage `failed_count=0` |
