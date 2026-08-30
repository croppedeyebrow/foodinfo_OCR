# 0단계 — 개발 실행 규칙

## 작업 순서

1. 현재 branch, status, 변경 파일을 확인한다.
2. 현재 단계와 관련 코드·계약·테스트를 조사한다.
3. 변경 파일과 호환성 영향을 먼저 제시한다.
4. 현재 단계 범위만 구현한다.
5. 단위·계약·통합·회귀 테스트를 실행한다.
6. diff를 자체 검토하고 완료 보고를 작성한다.

## 아키텍처 제약

- Python 3.12를 기본으로 사용한다.
- 대량 변환은 Polars expression과 Parquet을 우선한다.
- Console route와 template에 변환·매칭·품질 업무 규칙을 작성하지 않는다.
- `PipelineService`와 독립 Stage Service가 실행을 담당한다.
- Dagster, Airflow, Spark, Kafka, Kubernetes를 추가하지 않는다.
- Rust는 별도 benchmark와 승인 없이는 추가하지 않는다.
- 기존 `console`, `crawler`, `ocr-parser`, `normalizer` 기능을 단계적으로 보존한다.

## 데이터 안전

- `datasets`와 `outcome`의 기존 결과를 임의 삭제·덮어쓰기하지 않는다.
- Raw·OCR·PDF 입력은 불변 데이터로 취급한다.
- 실패 레코드는 rejection 또는 quarantine에 보존한다.
- 새 결과는 임시 위치에서 생성하고 검증 성공 후 승격한다.
- 모든 artifact에 schema version, checksum, row count, code/rule version, source lineage를 기록한다.

## UI 원칙

- 사용자는 Console에서 단계별 버튼과 상태로 작업한다.
- 서버가 선행 단계·권한·입력·현재 상태를 다시 검증한다.
- 장시간 작업은 run을 생성하고 UI가 상태를 조회한다.
- 성공 단계 재실행은 멱등 처리하거나 새 버전으로 생성한다.
- CLI는 테스트·복구용 내부 인터페이스로만 남길 수 있으며 사용자 절차로 문서화하지 않는다.

## 중단 조건

- 계약 필드 의미나 도메인 임계값이 불명확하다.
- 기존 산출물의 삭제·이동이 필요하다.
- KFIA 분류 매핑이나 소비기한 선택 우선순위를 임의로 정해야 한다.
- 여러 단계의 계약을 동시에 깨야 한다.
- 운영 credential 또는 외부 권한이 필요하다.

## 완료 보고

```markdown
# 단계 완료 보고
## 결과 요약
## 변경 파일과 이유
## UI 및 데이터 흐름 변화
## 계약·환경변수·migration 변화
## 실행한 테스트와 결과
## 기존 기능 호환성
## 보안·성능·데이터 안전 고려
## 남은 작업과 다음 단계 진입 조건
```
