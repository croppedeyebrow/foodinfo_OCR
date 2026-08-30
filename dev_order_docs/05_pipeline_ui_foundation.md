# 5단계 — UI 기반 Pipeline Stage 실행 기반

## 목표

Dagster 대신 Console UI에서 Stage를 실행하고 상태·진행률·결과를 확인하는 공통 기반을 구현한다.

## 구조

```text
Browser → Console Route/API → PipelineService → Stage Service
                                      ↓
                         Metadata Repository + Artifact Store
```

## API 예시

```text
POST /api/pipeline/batches/{batch_id}/stages/{stage}/runs
GET  /api/pipeline/runs/{run_id}
GET  /api/pipeline/batches/{batch_id}/status
POST /api/pipeline/runs/{run_id}/retry
```

## UI 공통 요소

- 단계 상태: 대기/실행 가능/실행 중/성공/실패/검토 필요
- 입력 artifact·checksum·버전
- 처리 건수와 진행률
- 오류 코드·사용자용 설명
- 결과 artifact와 품질 요약
- 허용된 단계 재실행

## 실행 규칙

- 서버가 선행 단계 성공 여부를 검사한다.
- route에는 업무 규칙을 두지 않는다.
- 장시간 작업은 run을 먼저 만들고 백그라운드에서 실행한다.
- UI는 상태 endpoint를 주기적으로 조회한다.
- 프로세스 재시작 시 RUNNING 상태 복구 정책을 둔다.
- 초기 규모에서는 Celery·Redis를 추가하지 않고 안전한 로컬 실행 방식으로 시작한다.

## 완료 조건

- fixture Stage를 UI에서 시작하고 완료 상태를 확인할 수 있다.
- 실패 원인이 UI에 표시되고 새 attempt로 재실행 가능하다.
- 중복 클릭이 중복 실행을 만들지 않는다.
- 기존 수집 UI가 회귀하지 않는다.
