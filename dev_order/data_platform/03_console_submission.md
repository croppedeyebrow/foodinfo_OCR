# 3단계 — 팀원용 Console 제출 경계

## 목표

팀원이 기존 UI에서 OCR 완료 후 검증된 배치를 제출할 수 있게 하며, 플랫폼 내부 기능은 노출하지 않는다.

## 신규 UI 단계

```text
4. 배치 검증 및 제출
```

표시 항목:

- batch ID와 member
- 발견·수집·OCR 성공/실패 수
- schema/parser version
- 필수 파일 존재 여부
- checksum 상태
- `READY`, `ACCEPTED`, `REJECTED` 상태

## 허용 동작

- 기존 batch 선택
- local validation 실행
- submission manifest 생성
- accepted inbox로 원자적 제출
- validation report 다운로드

## 금지 동작

- 식약처 parser 실행
- reconcile/quality/publish 실행
- Dagster 전체 job 실행
- pipeline DB 직접 수정
- Backend 적재
- 임의 shell command 입력

## 구현 원칙

1. 기존 command builder allowlist 방식을 유지한다.
2. `batch_id`는 path traversal이 불가능한 형식으로 검증한다.
3. 제출은 임시 디렉터리에 복사·검증 후 atomic rename한다.
4. 동일 checksum batch는 중복 접수하지 않는다.
5. 제출 실패가 기존 outcome을 손상시키지 않는다.
6. Console 메모리 상태와 별개로 submission 상태를 manifest에서 복구한다.

## 보안 주의

현재 Docker socket mount는 로컬 신뢰 환경에서만 허용한다. Console을 외부 네트워크에 공개하지 않는다. 서버화 시 Job API/Worker 구조로 교체하는 별도 ADR을 작성한다.

## 테스트

- 정상 제출
- 필수 파일 누락
- 잘못된 member/batch ID
- checksum 불일치
- 중복 제출
- 제출 중 예외 후 원본 보존
- Console 재시작 후 상태 복구

## 완료 조건

- 팀원이 CLI 없이 1~4단계를 완료할 수 있다.
- Console을 통해 플랫폼 관리 작업을 실행할 수 없다.
- 제출된 batch가 contract를 만족한다.

## AI 지시문

```text
기존 FastAPI/Jinja Console에 '배치 검증 및 제출' 단계만 추가해.
기존 1·2·2.5·3 route와 command를 변경하지 말고 arbitrary command 실행 경로를 만들지 마.
제출은 idempotent하고 실패 시 outcome 원본을 보존해야 해.
```
