# Collection 저장소 기준선 (01_repository_baseline)

조사 시점: 2026-08-08  
Git branch: `master` (origin/master 추적)  
범위: 코드 변경 없이 현재 Console / crawler / ocr-parser / normalizer / Compose / 데이터 경로 / 테스트 상태 기록

---

## 1. 저장소 구조 요약

| 경로 | 역할 |
|---|---|
| `apps/console` | FastAPI + Jinja/HTMX 단계 UI, Docker 작업 실행 |
| `apps/crawler` | Playwright 발견·상세 수집 CLI |
| `apps/ocr-parser` | 이미지 텍스트 판별·PaddleOCR·DOM 병합 CLI |
| `apps/normalizer` | PostgreSQL 연결 `health`만 존재 |
| `contracts/ocr_record.schema.json` | OCR raw 레코드 JSON Schema (`schema_version` const `1.0`) |
| `datasets/` | 원본·중간 산출물 (`discovery`, `crawl_raw`, `detail_images`, `ocr_raw` 등) |
| `outcome/{member}/{batch_id}/` | 팀원별 최종 `products.csv` / `failures.csv` |
| `compose.yaml` | `console`, `crawler`, `ocr-parser`, `normalizer`, `postgres` |
| `tests/` | 공유 단위 테스트 (서비스별 `use_app`로 src 전환) |
| `start_console.py` / `.cmd` / `.sh` | Console 컨테이너 런처 (`HOST_PROJECT_DIR` 주입) |

---

## 2. Docker 서비스·리소스

| 서비스 | 이미지/빌드 | 볼륨 | platform / memory / shm | 기본 command |
|---|---|---|---|---|
| `console` | `docker/console.Dockerfile` | `./:/workspace`, `apps/console/src:/app/src`, **`/var/run/docker.sock`** | 포트 `${CONSOLE_PORT:-8787}` | uvicorn `src.main:app` reload |
| `crawler` | `docker/crawler.Dockerfile` | `apps/crawler/src`, `datasets→/data`, `tests` ro | shm `${CRAWLER_SHM_SIZE:-512m}`, mem `${CRAWLER_MEMORY_LIMIT:-2g}` | `python -m src.cli health` |
| `ocr-parser` | `docker/ocr-parser.Dockerfile` | `apps/ocr-parser/src`, `contracts` ro, `datasets→/data`, `outcome→/outcome`, `tests` ro | **`platform: linux/amd64`**, shm `${OCR_SHM_SIZE:-1g}`, mem `${OCR_MEMORY_LIMIT:-3g}` | `python -m src.cli health` |
| `normalizer` | `docker/normalizer.Dockerfile` | src, contracts, datasets | `depends_on` postgres healthy | `python -m src.cli health` |
| `postgres` | `postgres:17` | `postgres-data` volume | 포트 `${DB_PORT:-5432}` | healthcheck `pg_isready` |

### Nested Docker 위험 (기준선으로 고정)

- Console 컨테이너가 Docker socket을 마운트하고, 작업 시 `docker run`으로 crawler/ocr 이미지를 기동한다.
- Windows에서 `docker compose run`의 상대 볼륨이 깨지는 문제를 피하기 위해 `HOST_PROJECT_DIR` + `docker inspect` 기반 bind root를 사용한다.
- bind root가 `/workspace`로 떨어지면 live `apps/*/src` 마운트가 생략되어 **이미지에 구워진 구버전 CLI**가 실행될 수 있다.

---

## 3. 식별자·버전 규칙

| 항목 | 규칙 |
|---|---|
| `batch_id` | `YYYYMMDD-{member}-일련번호` (예: `20260807-jaeseong-001`) |
| `BATCH_MEMBER` | `.env` (예: `jaeseong` / `sunyeong` / `woohee`). outcome 경로·OCR 필터에 사용 |
| 멤버 소속 판정 | `batch_belongs_to_member`: `batch_id`를 `-`로 쪼갠 토큰에 `member` 포함 여부 |
| Console 제안 ID | `{오늘}-{BATCH_MEMBER}-001` |
| Discovery 재사용 | 동일 `batch_id` 디렉터리 존재 시 **거부** (`ensure_fresh_batch_dir`) |
| `OCR_SCHEMA_VERSION` / 계약 | `contracts/ocr_record.schema.json` required `schema_version` = `"1.0"` |
| `PARSER_VERSION` | `.env.example` 기본 `0.2.0` (process-batch 기본값과 동일, process-one 코드 기본은 `0.1.0`) |
| 이미지 리사이즈 | `OCR_MAX_IMAGE_SIDE` 기본 `1600` (0=비활성). 해시는 원본 기준 |

---

## 4. Console routes · command builders

### HTTP routes

| Method | Path | 역할 |
|---|---|---|
| GET | `/` | 홈 |
| GET | `/steps/discover` | 1단계 UI |
| GET | `/steps/collect` | 2단계 UI |
| GET | `/steps/classify` | 2.5단계 UI |
| GET | `/steps/ocr` | 3단계 UI |
| GET | `/batches` | 배치 목록 JSON |
| GET | `/jobs/status` | 작업 상태(HTMX) |
| POST | `/jobs/discover` | discover urls/search/category |
| POST | `/jobs/collect` | collect-details (`force` 옵션) |
| POST | `/jobs/classify` | classify-images (`force` 옵션) |
| POST | `/jobs/ocr` | process-batch (`offset`, `limit`) |
| GET | `/health` | 헬스 |

작업 상태는 **프로세스 메모리** (`JobRunner`) 단일 잠금. 동시 1잡.

### Command builders → CLI

| Builder | Service | CLI |
|---|---|---|
| `build_discover_urls_command` | crawler | `discover-urls --input /data/input/product_urls.txt --batch-id …` |
| `build_discover_search_command` | crawler | `discover-search --keyword … --batch-id … --max-products … --max-scrolls …` |
| `build_discover_category_command` | crawler | `discover-category --batch-id … (--category-code\|--category-url) …` |
| `build_collect_details_command` | crawler | `collect-details --manifest /data/discovery/{id}/discovered_products.csv [--force]` |
| `build_classify_images_command` | ocr-parser | `classify-images --manifest /data/discovery/{id}/crawled_products.csv --batch-id … [--force]` |
| `build_process_batch_command` | ocr-parser | `process-batch --manifest /data/discovery/{id}/crawled_products.csv --batch-id … [--offset] [--limit]` |

실행 방식: Console 컨테이너 안이면 `docker run …`, 호스트면 `docker compose run --rm …`.

---

## 5. CLI 입출력 표

| 단계 | 실행 명령 | 입력 | 출력 | 재실행 규칙 | 담당 서비스 |
|---|---|---|---|---|---|
| health | `python -m src.cli health` | `/data` 볼륨 | stdout (Chromium/Paddle 버전) | 멱등 | crawler / ocr-parser / normalizer |
| 1-A 발견 | `discover-urls --input … --batch-id …` | `datasets/input/product_urls.txt` | `datasets/discovery/{batch_id}/discovered_products.csv`, `manifest.json`, (실패 시) `discovery_failures.csv` | **동일 batch_id 디렉터리 있으면 거부** | crawler |
| 1-B 발견 | `discover-search --keyword … --batch-id …` | 컬리 검색 (라이브) | 동일 discovery 산출물 | 동일 거부 | crawler |
| 1-C 발견 | `discover-category --category-code\|url … --batch-id …` | 컬리 카테고리 (라이브) | 동일 discovery 산출물 | 동일 거부 | crawler |
| 2 상세 | `collect-details --manifest …discovered_products.csv [--force]` | discovery CSV | `datasets/crawl_raw/{product_id}.json`, `datasets/detail_images/…`, `discovery/{batch_id}/crawled_products.csv`; 실패 → `outcome/{member}/{batch_id}/failures.csv` | `crawl_raw` 있으면 **스킵**(재사용) / `--force` 시 재수집; crawled CSV는 기존+신규 **병합**(force면 이번 성공분 덮어쓰기) | crawler |
| (호환) | `collect-batch --input … --batch-id …` | URL 목록 | crawl_raw + crawled_products | 순차 수집 (기존 호환) | crawler |
| (유틸) | `collect --input …` | URL 목록 | stdout URL만 | 상세 수집 안 함 | crawler |
| 2.5 판별 | `classify-images --manifest …crawled_products.csv --batch-id … [--force]` | crawled CSV + 이미지 | `datasets/discovery/{batch_id}/image_text_check.csv` | 이미 체크된 `image_path` **스킵** / `--force` 재검사; 신규는 image_path 기준 **병합 저장** | ocr-parser |
| 3 OCR | `process-batch --manifest … [--batch-id] [--offset] [--limit]` | crawled CSV + (선택) image_text_check | `datasets/ocr_raw/{product}_{hash}.json`, `outcome/{member}/{batch_id}/products.csv`; 실패 → `failures.csv` | `BATCH_MEMBER` 필터; `NO_TEXT` 스킵(체크 파일 있을 때); products는 **append**, 동일 source key면 **스킵**; offset/limit은 NO_TEXT 제외 후 청크 | ocr-parser |
| 3 단건 | `process-one --batch-id … --image …` | 단일 상품 인자 | ocr_raw + products.csv | pipeline 동일 dedupe | ocr-parser |
| normalizer | `health` | `DATABASE_URL` | DB 연결 확인만 | — | normalizer |

---

## 6. 데이터 경로 맵 (호스트 ↔ 컨테이너)

| 호스트 | crawler `/data` | ocr-parser | 비고 |
|---|---|---|---|
| `datasets/discovery/{batch_id}/` | `/data/discovery/…` | 동일 | discovered / crawled / image_text_check / manifest |
| `datasets/crawl_raw/` | `/data/crawl_raw/` | — | `{product_id}.json` |
| `datasets/detail_images/` | `/data/detail_images/` | 이미지 상대경로 기준 | |
| `datasets/ocr_raw/` | — | `/data/ocr_raw/` | OCR 원문 JSON |
| `datasets/input/` | `/data/input/` | — | `product_urls.txt` |
| `outcome/{member}/{batch_id}/` | (실패 CSV만, `OUTCOME_ROOT`) | `/outcome/…` | `products.csv`, `failures.csv` |
| `contracts/` | — | `/app/contracts` ro | |

Console(호스트 경로 해석): `datasets_root=project/datasets`, `outcome_root=project/outcome` (`OUTCOME_ROOT=/outcome`이면 호스트에서 `./outcome`으로 보정).

---

## 7. 호환성 고정 목록 (이후 단계에서 깨면 안 됨)

1. CLI 이름: `discover-urls`, `discover-search`, `discover-category`, `collect-details`, `classify-images`, `process-batch` (+ 기존 `collect`, `collect-batch`, `process-one`, `health`)
2. Console 단계 경로 `/steps/*`, job POST `/jobs/*`
3. 경로 패턴: `datasets/discovery/{batch_id}/{discovered_products|crawled_products|image_text_check}.csv`, `outcome/{BATCH_MEMBER}/{batch_id}/products.csv`
4. Compose 서비스명: `console`, `crawler`, `ocr-parser`, `normalizer`, `postgres`
5. `batch_id` / `BATCH_MEMBER` 토큰 포함 규칙
6. OCR 계약 `schema_version: "1.0"`, products CSV 컬럼 세트 (`PRODUCT_COLUMNS`)

---

## 8. 테스트 기준선 결과 (2026-08-08)

### 검증 명령 실행 결과

| 명령 | 결과 |
|---|---|
| `docker compose config` | OK (services: postgres, normalizer, ocr-parser, console, crawler) |
| `docker compose build crawler ocr-parser console` | OK (Docker Desktop 기동 후) |
| `crawler compileall /app/src` | OK |
| `ocr-parser compileall /app/src` | OK |
| `console compileall /app/src` | OK |
| 컨테이너 `pytest /app/tests -m "not integration"` (전체 마운트) | **실패(수집 단계)** — 아래 기존 이슈 |
| 서비스 범위 컨테이너 pytest | OK — 아래 수치 |
| 호스트 전체 `pytest tests -m "not integration"` | **8 failed, 65 passed** — 수집 순서 이슈 |
| 호스트 분리 실행 | console 29 / crawler계 28 / ocr계 16 전부 pass |

### 컨테이너 서비스 범위 (회귀 기준선으로 권장)

```text
crawler:  test_discovery + test_exporters + test_field_extractor + test_url_parser
          → 26 passed, 2 skipped

ocr-parser: test_disclosure_parser + test_batch_member_filter + test_text_presence
            + test_merge_policy + test_image_preprocess
          → 16 passed
```

### 기존 실패 vs 신규 실패 구분

| 증상 | 분류 | 설명 |
|---|---|---|
| 컨테이너에서 `tests/` 전체 수집 시 `test_console*`, `test_start_console` ImportError | **기존** | crawler/ocr 이미지에 console `src`·`start_console` 없음. 공유 `tests/` 마운트 구조 |
| crawler 전체 수집 시 `test_image_preprocess` PIL 없음 | **기존** | crawler 이미지에 Pillow 없음 (ocr-parser에는 있음) |
| 호스트에서 tests 일괄 실행 시 `test_console` 8건 `src.runner` ImportError | **기존** | 앞선 앱의 `src`가 sys.path에 남아 console import가 깨짐. **파일 분리 실행 시 통과** |
| 서비스 범위 단위 테스트 실패 | **없음** | 기준선 통과 |

integration 마커(`@pytest.mark.integration`, 라이브 컬리)는 본 단계에서 실행하지 않음.

---

## 9. normalizer / postgres 현황

- `normalizer` CLI: `health`만 — `DATABASE_URL`로 `SELECT current_database(), current_timestamp`
- Silver/Polars/변환 로직 **없음**
- `postgres:17`는 Compose에 정의되어 있으나 collection 1·2·2.5·3 흐름은 DB에 의존하지 않음

---

## 10. 다음 단계 진입 조건 (참고)

`02_contracts_and_storage`는 본 문서의 CLI·경로·재실행 규칙을 깨지 않는 선에서 Manifest/계약/저장 계층을 추가한다.  
회귀 검증은 위 **서비스 범위 pytest** + Console builder 단위 테스트 분리를 기준으로 삼는다.
