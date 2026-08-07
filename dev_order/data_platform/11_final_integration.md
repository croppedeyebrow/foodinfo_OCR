# 11단계 — Docker 운영·테스트·점진 migration

## 목표

기존 팀원 실행법을 깨지 않고 platform 서비스를 추가하고 전체 테스트·롤백 절차를 완성한다.

## Compose Profile

### collector

- console
- crawler
- ocr-parser

### platform

- dagster-web
- dagster-daemon
- normalizer
- mfds-parser
- reconciler
- quality/publisher worker
- pipeline metadata DB

## 실행

팀원:

```bash
docker compose --profile collector up -d
```

재성:

```bash
docker compose --profile platform up -d
```

두 profile을 함께 실행할 수 있어야 하지만 credential과 network exposure는 분리한다.

## 테스트 계층

- contract test
- pure transformation unit test
- Polars golden test
- reconciliation rule test
- quality rule test
- Dagster asset test
- metadata repository integration test
- Console submission test
- end-to-end fixture pipeline
- Backend export contract test

실제 컬리와 운영 Backend를 CI에서 호출하지 않는다.

## Migration 단계

1. 기존 경로 read-only 기준선
2. 신규 contract 병행 생성
3. Console submit 기능 도입
4. accepted inbox와 metadata 기록
5. Silver/Gold shadow 생성
6. 기존 CSV와 비교 검증
7. Backend test import
8. 신규 경로를 공식화
9. 구경로 제거는 별도 승인

## 롤백

- 신규 platform profile 정지
- 기존 1·2·2.5·3 단계 계속 사용
- 기존 outcome/products.csv 유지
- migration 전 데이터 삭제 금지

## 완료 조건

- 팀원 기존 UI 실행법이 유지된다.
- fixture 한 batch가 제출부터 Gold까지 완료된다.
- platform 실패가 collection 결과를 손상시키지 않는다.
- CI와 로컬 Docker 명령이 일치한다.

## AI 지시문

```text
collector/platform Compose profile과 테스트 계층을 구성해.
기존 팀원 start-console 실행을 깨지 말고 shadow output 방식으로 점진 migration해.
volume 삭제나 구경로 제거는 수행하지 마.
```
