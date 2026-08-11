# Stage 05A 개발 지시서 — Console 전체 팀원 배치 검증·제출 통제

## 0. 문서 사용 방법

이 문서는 AI 개발 도구에 그대로 전달하여 구현을 지시하기 위한 문서다.

- 대상 저장소: `https://github.com/croppedeyebrow/foodinfo_OCR`
- 실행 순서: Stage 05 Dagster 오케스트레이션 완료 후, Stage 06 Polars Silver 변환 전에 수행한다.
- 작업 성격: Git 데이터 전달 구조는 유지하고, Console 4단계의 운영 권한과 팀원 선택 기능만 확장한다.
- 구현 전 저장소의 `AGENTS.md`, `dev_order/data_platform/00_execution_rules.md`, 현재 코드와 테스트를 먼저 읽고 따른다.
- 기존 사용자의 변경 사항을 보존하고, 이 작업과 무관한 파일은 수정하지 않는다.

---

## 1. 목표

현재 팀원들은 하나의 GitHub 저장소를 함께 사용하고 있으며, 수집 결과를 다음 경로에 커밋하고 있다.

```text
datasets/discovery/{batch_id}/
outcome/{member}/{batch_id}/
```

재성 운영자가 `git pull`하면 선영·우희가 커밋한 `products.csv`, `failures.csv`, discovery CSV 및 manifest를 함께 받을 수 있다.

이번 작업의 목표는 다음 두 가지다.

1. Console의 `4. 검증·제출` 화면에서 운영자가 전체 팀원의 배치를 선택하여 로컬 검증과 accepted inbox 제출을 수행할 수 있게 한다.
2. `datasets/inbox/accepted`, `datasets/silver`, `datasets/gold` 및 파이프라인 실행 저장소는 Git으로 공유하지 않고 운영자 로컬에서만 관리한다.

최종 역할은 다음과 같다.

| 역할 | 담당 작업 |
|---|---|
| 팀원 수집자 | 상품 발견, 상세 수집, OCR, 자기 배치 결과 Git push |
| 재성 운영자 | 전체 팀원 배치 조회, 로컬 검증, accepted 제출, Dagster 이후 단계 운영 |
| Dagster | accepted inbox 감지, 파티션 등록, Bronze 이후 파이프라인 실행 |

---

## 2. 반드시 유지할 현재 구조

### 2.1 Git으로 공유하는 데이터

다음 경로는 현재와 같이 Git 추적 대상으로 유지한다.

```text
datasets/discovery/{batch_id}/
outcome/jaeseong/{batch_id}/
outcome/sunyeong/{batch_id}/
outcome/woohee/{batch_id}/
```

팀원이 push하고 운영자가 pull하는 현재 전달 방식을 변경하지 않는다.

### 2.2 운영자 로컬에서만 관리하는 데이터

다음 경로는 Git 비추적 상태를 유지한다.

```text
datasets/inbox/accepted/**
datasets/silver/**
datasets/gold/**
datasets/quarantine/**
datasets/warehouse/**
```

`.gitkeep`은 유지할 수 있지만, 실제 실행 산출물을 강제로 Git에 추가하지 않는다.

다음과 같은 작업을 금지한다.

- accepted inbox 결과 커밋
- Silver 또는 Gold 산출물 커밋
- DuckDB/PostgreSQL 실행 데이터 커밋
- `.gitignore`에서 위 로컬 운영 경로 제외 규칙 제거
- 이미지, HTML, OCR 원본을 일반 Git 추적 대상으로 일괄 전환

---

## 3. 현재 문제

Console은 `.env`의 `BATCH_MEMBER`를 현재 사용자로 사용한다.

```env
BATCH_MEMBER=jaeseong
```

현재 `4. 검증·제출` API는 대략 다음 형태로 고정 검증한다.

```python
validate_batch_selection(batch_id, settings.batch_member)
```

그 결과 운영자가 Git pull로 다른 팀원의 결과를 보유하더라도 Console에서 해당 배치를 선택하거나 제출하기 어렵다.

`BATCH_MEMBER`의 기존 의미를 제거하거나 모든 단계에서 전역 팀원 선택으로 바꾸지 않는다. 1~3단계 수집 화면은 기존 로컬 작업자의 `BATCH_MEMBER`를 계속 사용한다.

---

## 4. 요구사항

### 4.1 운영자 설정 추가

`.env.example`에 다음 설정을 추가한다.

```env
# Console 실행 역할: COLLECTOR 또는 OPERATOR
CONSOLE_ROLE=COLLECTOR

# 검증·제출 책임자 식별자
CONSOLE_OPERATOR=jaeseong

# OPERATOR가 4단계에서 처리할 수 있는 원본 생산자 목록
ALLOWED_BATCH_MEMBERS=jaeseong,sunyeong,woohee
```

규칙은 다음과 같다.

- `BATCH_MEMBER`: 1~3단계 수집 작업의 기본 생산자다.
- `CONSOLE_ROLE`: `COLLECTOR`, `OPERATOR`만 허용한다.
- `CONSOLE_OPERATOR`: 제출 작업을 수행한 운영자 식별자다.
- `ALLOWED_BATCH_MEMBERS`: 운영자가 처리 가능한 데이터 생산자 allowlist다.
- 값의 앞뒤 공백을 제거하고 빈 항목을 제외한다.
- 설정값이 잘못되면 조용히 권한을 확대하지 말고 명확한 오류를 발생시킨다.
- 운영자 PC의 실제 `.env`에는 `CONSOLE_ROLE=OPERATOR`를 사용한다.

### 4.2 Console 1~3단계 동작 유지

다음 화면의 기존 동작과 `BATCH_MEMBER` 필터를 변경하지 않는다.

1. 발견
2. 상세
3. OCR

이번 작업은 `4. 검증·제출` 화면과 관련 API에 한정한다.

### 4.3 Console 4단계 팀원 선택

운영자 화면에 다음 입력을 추가한다.

```text
데이터 생산자: [전체 또는 jaeseong/sunyeong/woohee]
배치:          [선택 생산자의 미제출 배치]
운영자:        jaeseong (읽기 전용 표시)
```

구현 조건:

- 운영자는 `ALLOWED_BATCH_MEMBERS`에 포함된 팀원만 선택할 수 있다.
- 선택한 팀원의 `outcome/{member}` 아래 배치만 표시한다.
- 가능하면 `datasets/discovery/{batch_id}`도 존재하는 배치를 우선 정상 후보로 표시한다.
- 배치 목록은 이름순보다 최신 배치가 먼저 보이도록 정렬한다.
- 배치 ID와 선택 팀원이 일치하지 않으면 실행을 거부한다.
- `products.csv`가 없는 배치는 제출할 수 없도록 표시하거나 서버에서 거부한다.
- 이미 accepted inbox에 동일 배치가 존재하면 기존 submission 모듈의 멱등성 및 중복 정책을 따른다.
- 템플릿에 전달된 클라이언트 값만 신뢰하지 말고 서버에서 다시 검사한다.

### 4.4 검증 API 변경

`POST /jobs/validate-submission`이 `batch_id`와 `member`를 받도록 변경한다.

처리 순서는 다음과 같아야 한다.

1. 현재 Console 역할이 `OPERATOR`인지 검사한다.
2. 요청한 `member`가 `ALLOWED_BATCH_MEMBERS`에 포함됐는지 검사한다.
3. `validate_batch_selection(batch_id, member)`를 호출한다.
4. `outcome/{member}/{batch_id}`가 실제로 존재하는지 검사한다.
5. 기존 `build_validate_collection_command(batch_id, member)`를 사용한다.
6. 검증 결과와 생산자·운영자를 화면 로그 또는 요약에 표시한다.

권한 또는 입력 검증 실패 시 500 오류로 숨기지 말고 사용자에게 이해 가능한 4xx 오류 또는 HTMX 오류 응답을 제공한다.

### 4.5 제출 API 변경

`POST /jobs/submit`도 `batch_id`와 `member`를 받도록 변경한다.

처리 순서는 다음과 같아야 한다.

1. `CONSOLE_ROLE=OPERATOR` 여부 확인
2. `member` allowlist 확인
3. 배치 ID와 생산자 일치 확인
4. 필수 결과 파일 확인
5. 기존 `build_submit_collection_command(batch_id, member)` 실행
6. accepted inbox로 원자적 제출
7. 제출 성공 후 Dagster Sensor가 기존 방식으로 감지할 수 있게 유지

제출 명령의 `--member`에는 Console 운영자가 아니라 원본 데이터 생산자를 전달한다.

예:

```text
실행자: jaeseong
데이터 생산자: woohee
명령 인자: --member woohee
```

### 4.6 수집자 모드의 제출 차단

`CONSOLE_ROLE=COLLECTOR`일 때:

- 4단계 화면에 검증·제출 버튼을 숨기거나 비활성화한다.
- API를 직접 호출해도 서버에서 `403`으로 거부한다.
- 화면 숨김만으로 권한 검사를 대체하지 않는다.
- 1~3단계는 기존대로 사용할 수 있어야 한다.

이 기능은 로컬 운영 절차를 분리하기 위한 것이다. 별도의 로그인·사용자 인증 시스템을 이번 단계에서 추가하지 않는다.

### 4.7 운영자 감사 정보

기존 `collection_submission` 계약을 깨지 않는 범위에서 운영자를 기록한다.

우선순위:

1. 파이프라인 메타데이터나 별도 submission audit metadata에 `submitted_by` 기록
2. 어렵다면 validation report 또는 Console 실행 요약에 기록

예시:

```json
{
  "batch_id": "20260808-woohee-017",
  "member": "woohee",
  "submitted_by": "jaeseong",
  "status": "ACCEPTED"
}
```

주의:

- `member`는 데이터 생산자 의미를 유지한다.
- `submitted_by` 때문에 기존 schema `1.0.0` 검증을 깨지 않는다.
- 계약 필수 필드 추가가 필요하다면 이 작업에서 임의 변경하지 말고 호환성 설계와 별도 schema 버전 계획을 문서화한다.

---

## 5. 주요 수정 대상

다음 파일을 먼저 검토한다.

```text
apps/console/src/config.py
apps/console/src/main.py
apps/console/src/runner.py
apps/console/src/summaries.py
apps/console/src/templates/step_submit.html
apps/console/src/templates/base.html
apps/console/src/templates/partials/summary.html
apps/normalizer/src/submission.py
apps/normalizer/src/cli.py
compose.yaml
.env.example
.gitignore
tests/test_console.py
tests/test_submission.py
```

수정 원칙:

- `runner.py`와 normalizer CLI가 이미 임의의 `--member`를 안전하게 받는다면 불필요하게 다시 설계하지 않는다.
- `submission.py`의 원자적 제출, checksum, schema 검증, 중복 제출 정책을 재사용한다.
- Console에서 normalizer의 비즈니스 검증 로직을 복제하지 않는다.
- 배치 생산자 검증은 공통 함수로 유지한다.
- 전역 변수나 하드코딩된 팀원 목록 대신 설정값을 사용한다.

---

## 6. 권장 내부 인터페이스

설정 모델은 다음 책임을 제공하도록 설계한다. 실제 프로젝트 스타일에 맞게 이름은 조정할 수 있다.

```python
class Settings:
    console_role: str
    console_operator: str
    allowed_batch_members: tuple[str, ...]

    @property
    def is_operator(self) -> bool: ...

    def ensure_member_allowed(self, member: str) -> None: ...
```

4단계 배치 조회는 생산자 정보를 잃지 않는 DTO를 반환하는 것이 좋다.

```python
class SubmissionBatchOption:
    member: str
    batch_id: str
    products_path: Path
    has_discovery: bool
    already_accepted: bool
```

단순 문자열 배열만 반환하여 배치 ID에서 매번 생산자를 추론하는 구조는 피한다.

---

## 7. 테스트 요구사항

기존 테스트를 유지하고 다음 테스트를 추가한다.

### 7.1 설정 테스트

- `ALLOWED_BATCH_MEMBERS=jaeseong,sunyeong,woohee` 파싱
- 공백과 빈 항목 정리
- 잘못된 `CONSOLE_ROLE` 거부
- 허용되지 않은 member 거부

### 7.2 배치 조회 테스트

- 운영자가 세 팀원의 배치를 모두 조회 가능
- 선택한 팀원별 필터 동작
- Git에 존재하는 `outcome/woohee/...` 배치 조회
- `products.csv`가 없는 배치 상태 표시 또는 제외
- accepted 완료 배치 상태 표시

### 7.3 검증·제출 API 테스트

- OPERATOR가 `woohee` 배치를 검증 가능
- OPERATOR가 `sunyeong` 배치를 제출 가능
- COLLECTOR의 직접 API 호출은 `403`
- allowlist 밖의 member는 거부
- `batch_id`와 member 불일치 거부
- 경로 순회 문자열 거부
- 제출 명령에 선택한 생산자 member가 전달됨
- `CONSOLE_OPERATOR`가 `--member`로 잘못 전달되지 않음

### 7.4 회귀 테스트

- 기존 재성 배치 검증·제출 성공
- 1~3단계의 `BATCH_MEMBER` 기반 동작 유지
- accepted 제출의 원자성 유지
- 중복 제출 정책 유지
- Dagster `accepted_collection_sensor` 테스트 성공
- 전체 기존 테스트 성공

---

## 8. 수동 검증 시나리오

운영자 `.env` 예시:

```env
BATCH_MEMBER=jaeseong
CONSOLE_ROLE=OPERATOR
CONSOLE_OPERATOR=jaeseong
ALLOWED_BATCH_MEMBERS=jaeseong,sunyeong,woohee
```

### 시나리오 A: 우희 배치 처리

1. `git pull origin master`
2. `outcome/woohee/{batch_id}/products.csv` 존재 확인
3. Console 4단계 이동
4. 생산자 `woohee` 선택
5. 우희 배치 선택
6. 로컬 검증 실행
7. 성공 결과 확인
8. accepted inbox 제출
9. `datasets/inbox/accepted/{batch_id}/manifest.json` 확인
10. Dagster Run 성공 확인

### 시나리오 B: 수집자 차단

1. `CONSOLE_ROLE=COLLECTOR`로 Console 시작
2. 1~3단계 사용 가능 확인
3. 4단계 버튼 비활성 또는 접근 안내 확인
4. 제출 API 직접 호출 시 `403` 확인

### 시나리오 C: 잘못된 생산자

다음 조합은 반드시 거부한다.

```text
batch_id=20260808-woohee-017
member=sunyeong
```

---

## 9. 실행 및 검증 명령

프로젝트 루트에서 실제 Compose 서비스명과 테스트 실행 방식을 확인한 뒤 실행한다.

권장 검증:

```cmd
docker compose run --rm console pytest -q
```

프로젝트에서 테스트가 normalizer 이미지에 통합되어 있다면 기존 저장소 명령을 따른다.

```cmd
docker compose run --rm normalizer pytest -q
```

Console 재빌드:

```cmd
docker compose up -d --build console
```

기존 CLI 동작도 회귀 확인한다.

```cmd
docker compose run --rm normalizer python -m src.cli validate-collection --batch-id 20260808-woohee-017 --member woohee
```

```cmd
docker compose run --rm normalizer python -m src.cli submit-collection --batch-id 20260808-woohee-017 --member woohee
```

---

## 10. 완료 조건

다음 조건을 모두 만족해야 완료다.

- [ ] Git 데이터 전달 구조를 변경하지 않았다.
- [ ] 운영자가 Console 4단계에서 전체 허용 팀원을 선택할 수 있다.
- [ ] 팀원을 선택하면 해당 팀원의 배치만 표시된다.
- [ ] 재성 운영자가 우희·선영 배치를 검증할 수 있다.
- [ ] 재성 운영자가 우희·선영 배치를 accepted inbox에 제출할 수 있다.
- [ ] 제출 manifest의 `member`가 원본 생산자로 유지된다.
- [ ] 운영자 식별 정보가 호환 가능한 위치에 기록된다.
- [ ] COLLECTOR는 서버 측 검사로 검증·제출이 차단된다.
- [ ] 1~3단계의 기존 수집 흐름이 변경되지 않았다.
- [ ] accepted, Silver, Gold, warehouse 실데이터가 Git에 추가되지 않았다.
- [ ] Dagster Sensor가 운영자가 제출한 타 팀원 배치를 감지한다.
- [ ] 신규 테스트와 기존 전체 테스트가 통과한다.

---

## 11. 구현 결과 보고 형식

작업 완료 후 다음 형식으로 보고한다.

```text
1. 변경한 파일 목록
2. Console 4단계 UI 변경 내용
3. 생산자(member)와 운영자(submitted_by) 구분 방식
4. 서버 측 권한 및 allowlist 검사 위치
5. Git 추적/비추적 정책 유지 여부
6. 실행한 테스트 명령과 결과
7. 우희 또는 선영 샘플 배치 수동 검증 결과
8. 남은 제한사항과 후속 작업
```

완료 조건을 충족하지 못한 항목을 성공한 것처럼 보고하지 않는다.
