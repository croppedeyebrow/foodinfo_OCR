# 10단계 — Backend 전달 계약

## 목표

Gold bundle을 서비스 Backend가 멱등하고 원자적으로 가져갈 수 있는 계약을 확정한다.

## 초기 방식

파일 bundle import를 사용한다. API·메시지 브로커는 별도 요구가 생기기 전까지 추가하지 않는다.

## Backend 처리

1. manifest·schema·checksum 검증
2. dataset version 중복 확인
3. transaction 단위 staging
4. 도메인 Service를 통한 upsert
5. publish 결과와 실패 원인 기록

## UI

- 배포 가능한 Gold version 목록
- manifest·품질 gate 상태
- 배포 요청·진행·성공·실패
- 이전에 배포한 version 이력
- 중복 배포 방지 메시지

## 보안 경계

- Backend credential은 OPERATOR 환경에만 둔다.
- 팀원 Console에 publish 기능과 credential을 노출하지 않는다.
- pipeline이 Backend 내부 모델을 import하지 않는다.

## 완료 조건

- 같은 dataset version이 중복 적재되지 않는다.
- 실패 시 부분 적재가 남지 않는다.
- Backend 데이터에서 Gold version과 source lineage를 찾을 수 있다.
- 실제 운영 Backend 호출 없이 fixture 통합 테스트가 가능하다.
