# Pipeline Metadata와 Lineage

## 추적 대상

- pipeline run
- 단계별 실행과 attempt
- 입력·출력 artifact
- schema/code/rule version
- checksum, row count, byte size
- 품질검사 결과
- Gold publish history

## 원칙

- 서비스 Backend DB와 pipeline metadata를 논리적으로 분리한다.
- 파일 payload 전체를 PostgreSQL에 넣지 않는다.
- 모든 Gold 결과에서 입력 batch와 artifact checksum을 역추적할 수 있어야 한다.
- 동일 batch·dataset version은 idempotent하게 처리한다.
