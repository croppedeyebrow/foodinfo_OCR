# 1단계 — 저장소 기준선 확정

## 목표

기존 UI와 수집 파이프라인의 실제 동작을 변경 없이 검증하고 이후 단계의 회귀 기준을 만든다.

## 조사 대상

- `README.md`
- `compose.yaml`
- `.env.example`
- `apps/console/src/main.py`
- `apps/console/src/runner.py`
- `apps/console/src/config.py`
- `apps/crawler/src`
- `apps/ocr-parser/src`
- `apps/normalizer/src/cli.py`
- `contracts`
- `datasets`, `outcome`, `tests`

## 확인 내용

1. Console route와 command builder 목록을 기록한다.
2. crawler·ocr-parser CLI command, 입력, 출력을 표로 만든다.
3. 단계별 파일 생성 위치와 overwrite/skip 규칙을 기록한다.
4. `batch_id`, `BATCH_MEMBER`, schema/parser version 규칙을 확인한다.
5. Docker volume, platform, memory, shm 설정을 기록한다.
6. 현재 테스트를 실행하고 결과를 기준선으로 저장한다.
7. Docker socket mount와 nested `docker run` 구조를 위험사항으로 기록한다.

## 산출물

`dev_docs/data_platform/current_baseline.md`에 다음 표를 작성한다.

```text
단계 | 실행 명령 | 입력 | 출력 | 재실행 규칙 | 담당 서비스
```

## 이 단계에서 금지

- 코드 수정
- 폴더 이동
- 의존성 추가
- Compose 서비스명 변경
- 결과 데이터 삭제

## 검증 명령

```bash
docker compose config
docker compose build crawler ocr-parser console
docker compose run --rm crawler python -m compileall -q /app/src
docker compose run --rm ocr-parser python -m compileall -q /app/src
docker compose run --rm crawler pytest -q /app/tests -m "not integration"
docker compose run --rm ocr-parser pytest -q /app/tests -m "not integration"
```

## 완료 조건

- 기존 1·2·2.5·3 단계의 입출력이 문서화됐다.
- 현재 실패 테스트와 신규 작업으로 생긴 실패를 구분할 수 있다.
- 호환성을 깨면 안 되는 CLI와 파일 경로가 확정됐다.

## AI 지시문

```text
이 단계는 read-only 조사다. 저장소를 수정하지 말고 현재 Console, crawler,
ocr-parser, normalizer, Compose, 데이터 경로를 분석해 current_baseline.md를 작성해.
실제 컬리 네트워크 수집은 수행하지 말고 로컬 검사와 단위 테스트만 실행해.
```
