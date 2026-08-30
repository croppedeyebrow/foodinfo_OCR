# 2단계 — 데이터 계약과 저장 계층

- **지시 문서**: `dev_order_docs/02_contracts_and_storage.md`
- **완료일**: 2026-08
- **상태**: DONE

## 결과 요약

CSV 직접 연결 대신 **versioned JSON Schema 계약**과 **checksum**으로 단계 간 데이터를 연결하는 기반을 구춡했다. Collection 제출(accepted inbox) 경로와 검증·원자 제출 로직이 동작한다.

## 변경 파일과 이유

| 영역 | 주요 파일 | 이유 |
|---|---|---|
| 스키마 | `contracts/*.schema.json` | collection_submission, kurly_raw_product, gold 등 v1 계약 |
| Normalizer | `apps/normalizer/src/contracts.py` | Pydantic 모델·jsonschema 검증·버전 게이트 |
| Normalizer | `apps/normalizer/src/checksum.py` | canonical `content_hash` (SHA-256) |
| Normalizer | `apps/normalizer/src/submission.py` | 로컬 검증·accepted 원자 제출 |
| Normalizer | `apps/normalizer/src/adapters/products_csv.py` | products.csv → collection_submission 적응 |
| Normalizer CLI | `validate-collection`, `submit-collection` | 제출 파이프라인 진입점 |
| 테스트 | `tests/test_contracts.py`, `tests/test_submission.py` | 계약·제출·멱등성 |

## UI 및 데이터 흐름 변화

```text
outcome + discovery  →  validate-collection  →  validation_report.json
                     →  submit-collection   →  datasets/inbox/accepted/{batch_id}/
                                              ├─ manifest.json
                                              ├─ discovery/
                                              └─ outcome/
```

계층 (목표 파이프라인):

```text
Candidate → Accepted → Bronze → Silver → Reconciled → Quality → Gold
```

2단계에서 **Accepted**까지 구현. Bronze 이후는 6단계 이후.

## 계약·환경변수·migration 변화

### 저장 경로 (정의·부분 구현)

```text
datasets/inbox/accepted/{batch_id}     ← 구현됨
datasets/bronze/kurly/{batch_id}       ← 6단계
datasets/silver/kurly/{batch_id}       ← 6단계
datasets/reference/...                 ← 7단계
datasets/gold/...                      ← 9단계
```

### collection_submission v1.0.0 필수 필드

`schema_version`, `batch_id`, `member`, `status`, `content_hash`, `row_count`, `products`, `artifacts` 등.

### 제출 정책

- 임시 디렉터리 생성 → manifest 검증 → `os.replace` 원자 승격
- 동일 checksum 중복 제출은 멱등 (`duplicate=true`)
- 다른 내용의 동일 batch_id는 `BATCH_ALREADY_ACCEPTED_DIFFERENT_CONTENT` 거부

## 실행한 테스트와 결과

```text
tests/test_contracts.py      — 스키마·checksum·버전 게이트
tests/test_submission.py     — 검증·제출·멱등·경로 traversal 거부
```

## 기존 기능 호환성

- 기존 `products.csv` / discovery CSV 구조 유지.
- Console 1~3단계 수집·OCR 흐름 변경 없음.

## 보안·성능·데이터 안전 고려

- `batch_id`·`member` 패턴 검증으로 경로 순회 방지.
- invalid 레코드는 validation_report `errors`에 보존, silent drop 없음.
- manifest `additionalProperties: false` — 계약 외 필드 금지.

## 잔여 과제·다음 단계 진입 조건

- [x] 결정적 checksum
- [x] accepted 계약 호환
- [x] invalid record 유실 없음
- → **3단계** 메타데이터 DB 기록

## 레거시·주의사항

- CSV는 공식 source of truth가 아니라 **호환·검토 view**.
- KFIA·Gold 계약 스키마 파일은 존재하나 **생산 파이프라인은 미구현**.
