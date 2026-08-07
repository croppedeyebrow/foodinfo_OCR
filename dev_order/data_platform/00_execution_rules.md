# 0단계 — AI 개발 실행 프로토콜

## 목적

AI가 저장소 전체를 임의 재설계하거나 여러 단계를 동시에 구현하지 않도록 작업 단위를 통제한다.

## 매 작업 시작 지시문

```text
먼저 AGENTS.md, dev_order/README.md, dev_docs/data_platform/00_overview.md,
현재 READY 또는 IN_PROGRESS 단계 문서를 끝까지 읽어.

현재 Git 상태와 관련 파일을 조사한 뒤 구현 계획과 영향 파일을 먼저 제시해.
승인된 현재 단계의 범위만 구현하고 기존 사용자 변경을 보존해.
기존 Console 1·2·2.5·3 흐름과 CLI 호환성을 깨지 마.
실제 컬리 사이트, 운영 DB, 외부 서비스는 테스트에서 호출하지 마.
검증 명령을 실행하고 지정된 완료 보고 형식으로 결과를 정리해.
```

## AI 작업 순서

1. 현재 branch, status, 변경 파일 확인
2. 현재 단계 관련 파일 조사
3. 계약과 호환성 영향 분석
4. 구현 계획 제시
5. 최소 범위 구현
6. format/lint/type/test
7. diff 자체 검토
8. 완료 보고

## 중단하고 질문할 조건

- 문서와 현재 코드가 충돌
- schema field 의미가 불명확
- 기존 output을 이동·삭제해야 함
- credential 또는 외부 권한 필요
- 실제 사이트 호출 없이는 검증 불가
- Rust 도입 gate가 충족되지 않음
- Backend ERD와 Gold 계약이 불일치
- 여러 단계의 계약을 동시에 바꿔야 함

## 금지 프롬프트 해석

- “적절히 처리”를 임의 도메인 규칙 생성으로 해석하지 않는다.
- failing test를 삭제하거나 skip해 통과시키지 않는다.
- broad exception으로 오류를 숨기지 않는다.
- fixture를 실제 성공 결과처럼 하드코딩하지 않는다.
- 구조 개선을 이유로 무관한 코드까지 정리하지 않는다.

## Definition of Done

- 요구사항과 비요구사항 준수
- contract/version 영향 기록
- unit/integration test 통과
- 기존 collection 회귀 없음
- migration/rollback 경로 존재
- 문서와 실행 명령 업데이트
- 남은 위험 명시

## 완료 보고 템플릿

```markdown
# 단계 완료 보고

## 결과 요약
## 변경 파일 및 이유
## 데이터 흐름 변화
## 계약/환경변수/migration 변화
## 실행한 검증과 결과
## 기존 기능 호환성
## 보안·성능 고려사항
## 남은 작업과 다음 단계 진입 조건
```
