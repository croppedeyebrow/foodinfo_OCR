# 11단계 — 최종 통합·Dagster 제거·Docker·E2E

## 목표

UI 기반 파이프라인을 공식 경로로 전환하고 Dagster 의존성을 안전하게 제거한다.

## 최종 서비스

```text
console
crawler
ocr-parser
normalizer 또는 pipeline
postgres
```

## 제거 대상

- Compose의 `dagster` 서비스와 profile
- `dagster-home` volume
- `DAGSTER_HOME`, `DAGSTER_PORT` 등 환경변수
- `orchestration/`
- orchestration Dockerfile·requirements
- Dagster adapter와 Asset·Job·Sensor·Partition 테스트

삭제 전 같은 fixture에서 기존 경로와 UI Pipeline 결과를 비교하고, 사용자 승인 없이 datasets·outcome·DB volume을 삭제하지 않는다.

## Docker 정리

- 루트 `.dockerignore` 추가
- datasets, outcome, Git 이력, 문서를 build context에서 제외
- 운영·개발 의존성 분리
- OCR 모델은 검증된 volume cache 사용
- 서비스별 이미지는 유지하고 불필요한 공통 중복 layer를 정리

## E2E 시나리오

1. 팀원 fixture 배치 조회
2. 운영자 검증·accepted 제출
3. 컬리 Bronze·Silver
4. KFIA 기준 파일 등록·Reference Bronze·Silver
5. 대조·품질검토
6. Gold 생성
7. Backend test import
8. UI에서 run·품질·lineage 확인

## 회귀 테스트

- contract test
- 변환 unit/golden test
- metadata repository integration
- Console 권한·제출·Stage 실행
- reconciliation·quality rule
- Gold·Backend import
- 기존 crawler/OCR 비통합 테스트

## 롤백

- 신규 Pipeline Stage 실행을 중지해도 기존 수집·OCR·outcome은 유지한다.
- 공식 전환 전에는 기존 Dagster 코드를 별도 Git commit/tag에서 복구할 수 있어야 한다.
- 데이터 삭제가 아니라 코드 경로 전환으로 롤백한다.

## 완료 조건

- 사용자가 CLI나 Dagster UI 없이 전체 흐름을 완료한다.
- fixture 한 배치가 제출부터 Gold까지 성공한다.
- 플랫폼 실패가 기존 수집 결과를 손상시키지 않는다.
- 저장소와 Compose에서 Dagster 런타임 의존성이 제거된다.
- README·AGENTS.md·환경변수·운영 문서가 최종 구조와 일치한다.
