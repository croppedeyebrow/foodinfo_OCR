# 4단계 — 전체 팀원 배치 검증·제출 UI

- **지시 문서**: `dev_order_docs/04_operator_submission_ui.md`
- **완료일**: 2026-08-30
- **상태**: DONE

## 결과 요약

운영자(`OPERATOR`)가 allowlist 내 **모든 팀원 배치**를 Console에서 검증·accepted 제출할 수 있게 했다. `COLLECTOR`는 검증·제출 API가 **403**으로 거부된다. 원본 생산자(`member`)와 제출 실행자(`submitted_by`)를 분리해 감사 기록을 남긴다.

## 변경 파일과 이유

| 영역 | 주요 파일 | 이유 |
|---|---|---|
| Console 설정 | `apps/console/src/config.py` | `CONSOLE_ROLE`, `CONSOLE_OPERATOR`, `ALLOWED_BATCH_MEMBERS` |
| Console 권한 | `apps/console/src/auth.py` | OPERATOR 판별·배치 allowlist 해석 |
| Console API/UI | `apps/console/src/main.py` | `/steps/submit`, 검증·제출 job, 403 거부 |
| Console UI | `apps/console/src/templates/step_submit.html` | 생산자 필터·다중선택·상태 표시 |
| Console UI | `base.html`, `home.html` | 네비: 4.팀결과 / 5.검증·제출 (OPERATOR) |
| Console 요약 | `apps/console/src/summaries.py` | `summarize_operator_batches`, allowlist 검증 |
| Console runner | `apps/console/src/runner.py` | `submit-collection --submitted-by` 전달 |
| Normalizer | `apps/normalizer/src/submission.py` | `submitted_by`, `submission_audit.json` |
| Normalizer CLI | `apps/normalizer/src/cli.py` | `--submitted-by` 옵션 |
| 환경 예시 | `.env.example` | 역할 관련 변수 문서화 |
| 테스트 | `tests/test_console.py`, `tests/test_submission.py` | 역할·403·감사 기록 |

## UI 및 데이터 흐름 변화

### 역할

```env
BATCH_MEMBER=jaeseong          # 수집 생산자 (팀원 PC)
CONSOLE_ROLE=OPERATOR          # 운영자 PC
CONSOLE_OPERATOR=jaeseong      # 제출 실행자
ALLOWED_BATCH_MEMBERS=jaeseong,sunyeong,woohee
```

### 흐름

```text
팀원(COLLECTOR): 1~3단계 수집·OCR → Git push
운영자(OPERATOR): pull → /steps/submit
  → [계약 검증]  → outcome/.../validation_report.json
  → [accepted 제출] → datasets/inbox/accepted/{batch_id}/
                      ├─ manifest.json          (member = 원본 생산자)
                      ├─ submission_audit.json  (submitted_by = 운영자)
                      └─ discovery/ + outcome/
```

### Console 네비게이션

| 단계 | 경로 | 대상 |
|---:|---|---|
| 4 | `/steps/team` | 전원 (읽기 전용 팀 결과) |
| 5 | `/steps/submit` | OPERATOR (검증·제출) |

상태 표시: 미검증 / 검증성공 / 제출완료 / 실패

## 계약·환경변수·migration 변화

- `collection_submission` schema **1.0.0 변경 없음** (`additionalProperties: false` 유지).
- `submitted_by`는 manifest가 아닌 **`submission_audit.json`** 및 `validation_report.json`에 기록.
- `CONSOLE_PLATFORM_MODE=true`는 하위 호환용으로 `OPERATOR`로 취급.

### submission_audit.json 예시

```json
{
  "schema_version": "1.0.0",
  "batch_id": "20260811-woohee-002",
  "member": "woohee",
  "submitted_by": "jaeseong",
  "submitted_at": "2026-08-30T13:00:00+09:00",
  "duplicate": false
}
```

## 실행한 테스트와 결과

```text
pytest tests/test_console.py tests/test_submission.py — 45 passed
```

주요 검증:
- `CONSOLE_ROLE=COLLECTOR` → `/jobs/submit` 403
- allowlist 밖 생산자 배치 거부
- 운영자 제출 시 `submission_audit.json`·`validation_report.submitted_by` 기록
- manifest `member`는 원본 생산자 유지

## 기존 기능 호환성

- 1~3단계 수집·OCR Console/CLI **회귀 없음**.
- 2단계 accepted 원자성·중복 정책 유지.
- 팀 결과(`/steps/team`) 읽기 전용 유지.

## 보안·성능·데이터 안전 고려

- UI 버튼 숨김만이 아니라 **서버 측 OPERATOR 검증**.
- `validate_operator_batch_selection`: allowlist + batch_id 소유 + 경로 패턴.
- 제출은 기존과 동일하게 배치 **순차 큐** 실행 (Docker 메모리 보호).

## 잔여 과제·다음 단계 진입 조건

- [x] 운영자가 타 팀원 배치 검증·제출
- [x] COLLECTOR API 403
- [x] member / submitted_by 분리
- [x] Git·accepted 원자성 유지
- → **5단계** `PipelineService` + Console Stage API (Dagster UI 대체)

## 레거시·주의사항

| 항목 | 상태 | 조치 예정 |
|---|---|---|
| `/steps/platform`, Dagster intake job | **레거시 잔존** | Console에서 제거 또는 11단계와 함께 삭제 |
| `start_console.py --platform` | Dagster UI 기동 | 11단계 제거 |
| `orchestration/`, compose `dagster` | 코드·서비스 잔존 | 11단계 제거 |
| 6단계 Dagster 네비 | 4단계 구현 시 일시 추가됨 | **지시 문서와 불일치** — 5단계 전 Console 정리 권장 |

`dev_order_docs` 확정 방향: **Dagster 제거, Console UI에서 Stage 실행**. 물리 삭제는 11단계, Console 노출 정리는 5단계 착수 전 권장.
