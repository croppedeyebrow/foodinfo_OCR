# 4단계 — 전체 팀원 배치 검증·제출 UI

## 목표

팀원은 수집·OCR 결과를 Git에 push하고, 운영자는 pull한 뒤 Console에서 모든 허용 팀원의 배치를 검증·accepted 제출한다.

## 역할

```env
BATCH_MEMBER=jaeseong
CONSOLE_ROLE=OPERATOR
CONSOLE_OPERATOR=jaeseong
ALLOWED_BATCH_MEMBERS=jaeseong,sunyeong,woohee
```

- `BATCH_MEMBER`: 수집 단계의 기본 생산자
- `CONSOLE_OPERATOR`: 검증·제출 실행자
- `ALLOWED_BATCH_MEMBERS`: 운영자가 처리할 수 있는 생산자
- `COLLECTOR`: 수집·OCR만 가능
- `OPERATOR`: 전체 허용 팀원 검증·제출 가능

## UI

```text
생산자 [전체/jaeseong/sunyeong/woohee]
배치   [선택 생산자의 미제출 배치]
운영자 jaeseong
상태   미검증/검증성공/제출완료/실패
[계약 검증] [accepted 제출]
```

## 서버 검증

- OPERATOR 역할
- member allowlist
- batch ID와 생산자 일치
- 경로 순회 방지
- `products.csv`와 필수 파일 존재
- accepted 중복 정책
- `member`와 `submitted_by` 분리

버튼을 숨기는 것만으로 권한을 구현하지 않는다. 1~4단계 기존 수집 흐름은 유지한다.

## 완료 조건

- 운영자가 우희·선영 배치를 UI에서 검증하고 제출할 수 있다.
- COLLECTOR의 직접 API 호출이 403으로 거부된다.
- manifest의 `member`는 원본 생산자로 유지된다.
- 운영자 감사 정보가 호환 가능한 metadata에 기록된다.
- Git 추적·비추적 정책과 accepted 원자성이 유지된다.
