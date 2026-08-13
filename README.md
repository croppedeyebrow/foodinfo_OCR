# 컬리 상품 발견·상세 크롤링·OCR 파서

컬리 상품을 URL 목록·검색어·카테고리로 발견하고, 상세페이지 DOM·이미지를 수집한 뒤 PaddleOCR로 고시정보를 보완하여 팀원·배치별 CSV를 만드는 Docker 기반 프로젝트입니다.

## 구성

- `crawler`: Playwright 기반 상품 발견 및 상세페이지 수집
- `ocr-parser`: PaddleOCR 기반 OCR, DOM·OCR 병합, 최종 CSV
- `console`: FastAPI 단계별 실행 UI (`docker compose` CLI 호출)
- `normalizer`: 계약 검증·products.csv adapter·pipeline metadata / (추후) Silver 정제
- `orchestration`: 관리자용 Dagster asset graph·batch partition·실행 job
- `contracts/`: versioned JSON Schema (`collection_submission`, Kurly/MFDS raw, Silver/Gold 등)
- `postgres`: 전용 schema의 pipeline metadata 저장

원본 이미지·크롤/OCR 원문 JSON은 `datasets`에 저장되며 Git에서 제외됩니다.  
발견 목록(`datasets/discovery/{배치ID}/`)과 최종 CSV(`outcome/{팀원}/{배치ID}/`)는 팀 공유용으로 남길 수 있습니다.

## 처리 흐름

```text
[URL 목록 / 검색어 / 카테고리]
  → 1) 상품 발견 → discovered_products.csv
  → 2) 상세페이지 수집 → crawl_raw JSON + detail_images + discovery/{배치ID}/crawled_products.csv
  → 3) OCR·병합 → ocr_raw JSON + outcome/{팀원}/{배치ID}/products.csv
```

배치 ID 형식: `YYYYMMDD-팀원-일련번호` (예: `20260723-jaeseong-001`)

## 사전 준비

```cmd
cd /d C:\Dev\work_python\crowling_ocr_parser
docker compose build crawler
docker compose build ocr-parser
```

### 환경변수 (팀원별 `.env`)

`.env`는 Git에 올리지 않습니다(비밀번호·개인 설정).  
대신 **템플릿인 `.env.example`만 공유**하고, 각자 로컬에서 복사해 씁니다.

```cmd
copy .env.example .env
```

그다음 `.env`에서 자기 이름만 바꿉니다.

```dotenv
BATCH_MEMBER=jaeseong
```

| 팀원 | `BATCH_MEMBER` 값 | 결과 저장 위치 |
|---|---|---|
| 재성 | `jaeseong` | `outcome/jaeseong/` |
| 선영 | `sunyeong` | `outcome/sunyeong/` |
| 우희 | `woohee` | `outcome/woohee/` |

공통 설정(타임아웃, OCR 버전 등)은 `.env.example`에 두고, 개인 값만 `.env`에서 수정하면 됩니다.  
`.env.example`을 변경하면 PR로 공유하고, 팀원은 필요 시 자기 `.env`에 반영합니다.

컨테이너 상태 확인:

```cmd
docker compose run --rm crawler
docker compose run --rm ocr-parser
```

## 단계별 실행 UI (Console)

브라우저에서 1 → 2 → 2.5 → 3 파라미터를 확인·실행합니다.  
콘솔 **앱 자체는 Docker 컨테이너**로 뜹니다.  
다만 컨테이너를 켜는 **호스트 런처**가 필요해서, Mac에서 `python`이 없으면 오류가 납니다  
(파이프라인 crawler/ocr가 Python을 못 찾는 문제가 아님).

**권장 (OS별, 호스트 Python 불필요)**

| OS | 실행 |
|---|---|
| Windows | `start-console.cmd` |
| Mac / Linux | `bash start-console.sh` |

```bash
# Mac — Docker만 있으면 됨 (python 불필요)
bash start-console.sh
```

```cmd
REM Windows
start-console.cmd
```

Docker Desktop이 꺼져 있으면 실행 여부를 묻고, 엔진이 준비될 때까지 대기합니다.  
프롬프트 없이 바로 켜려면: `bash start-console.sh -y` / `start-console.cmd -y` / `python start_console.py -y`

런처가 `HOST_PROJECT_DIR`을 넘깁니다. 이게 있어야 콘솔 안에서 crawler/ocr 마운트가 맞습니다.

Python이 있는 환경에서 동일하게:

```bash
# Mac
python3 start_console.py

# Windows
python start_console.py
```

플랫폼 관리자는 Git에서 제외되는 개인 `.env`에 다음 값을 설정합니다.

```dotenv
CONSOLE_PLATFORM_MODE=true
```

이후 평소처럼 실행해도 Console과 Dagster가 함께 시작됩니다.

```powershell
python start_console.py
```

이 모드는 Console(`8787`)과 Dagster(`3000`)를 함께 열고, `Ctrl+C`로
Console과 Dagster를 함께 정지합니다. PostgreSQL volume은 삭제하지 않습니다.
팀원 기본 실행에는 Dagster가 포함되지 않습니다. Dagster 포트는
`--dagster-port 3100`처럼 변경할 수 있습니다. 브라우저에는 서비스가 준비될
때까지 임시 연결 화면이 표시되고, health 응답을 받으면 자동 이동합니다.
일회성 강제 실행은 `--platform`, 개인 설정을 무시하고 Console만 실행하려면
`--console-only`를 사용합니다.

포트 변경: `bash start-console.sh 8790` / `start-console.cmd 8790`  
브라우저: [http://127.0.0.1:8787](http://127.0.0.1:8787)

동시에 하나의 작업만 실행됩니다. OCR/판별은 Windows·Linux(amd64) 환경을 권장합니다.

## 1단계: 상품 발견 (Discovery)

검색·카테고리에서는 상세/OCR을 바로 하지 않고, 상품 ID·URL만 모아 CSV로 저장합니다.  
동일 `batch-id` 디렉터리가 이미 있으면 덮어쓰지 않고 거부합니다. 새 배치 ID를 쓰세요.

### 1-A. URL 목록

입력 파일: `datasets/input/product_urls.txt`

```text
# 빈 줄과 # 주석은 무시한다.
https://www.kurly.com/goods/5047857?collectionCode=2607-vacanceonestop-home
```

```cmd
docker compose run --rm crawler python -m src.cli discover-urls --input /data/input/product_urls.txt --batch-id 20260723-jaeseong-001
```

### 1-B. 검색어

```cmd
docker compose run --rm crawler python -m src.cli discover-search --keyword "육류" --batch-id 20260723-jaeseong-002 --max-products 5 --max-scrolls 3
```

### 1-C. 카테고리

`--category-code` 또는 `--category-url` 중 **하나만** 지정합니다.

```cmd
docker compose run --rm crawler python -m src.cli discover-category --category-code 910 --batch-id 20260723-jaeseong-003 --max-products 5 --max-scrolls 3
```

```cmd
docker compose run --rm crawler python -m src.cli discover-category --category-url "https://www.kurly.com/categories/910" --batch-id 20260723-jaeseong-003 --max-products 5 --max-scrolls 3
```

개발 시에는 `--max-products 5 --max-scrolls 3`처럼 소량으로 시작하는 것을 권장합니다.  
기본값은 `max-products=20`, `max-scrolls=10`입니다 (상한: 상품 500, 스크롤 100).

### 1단계 산출물

```text
datasets/discovery/{배치ID}/discovered_products.csv
datasets/discovery/{배치ID}/manifest.json
datasets/discovery/{배치ID}/discovery_failures.csv   (실패 시)
```

## 2단계: 상세페이지 수집

발견 CSV를 읽어 상품 상세를 순차 수집합니다.  
이미 `datasets/crawl_raw/{상품ID}.json`이 있으면 기본적으로 건너뜁니다. 다시 받으려면 `--force`를 사용합니다.

```cmd
docker compose run --rm crawler python -m src.cli collect-details --manifest /data/discovery/20260723-jaeseong-002/discovered_products.csv
```

강제 재수집:

```cmd
docker compose run --rm crawler python -m src.cli collect-details --manifest /data/discovery/20260723-jaeseong-002/discovered_products.csv --force
```

### 2단계 산출물

```text
datasets/crawl_raw/{상품ID}.json
datasets/detail_images/{상품ID}_{순번}_{해시}.jpg
datasets/discovery/{배치ID}/crawled_products.csv
outcome/{팀원}/{배치ID}/failures.csv   (상세 수집 실패 시)
```

배치마다 CSV가 분리되어 팀원 간 Git 충돌을 줄입니다.

### (호환) URL에서 바로 상세 수집

발견 단계 없이 URL 파일만으로 상세 수집할 때:

```cmd
docker compose run --rm crawler python -m src.cli collect-batch --input /data/input/product_urls.txt --batch-id 20260723-jaeseong-001
```

## 2.5단계: 이미지 텍스트 판별 (권장)

상세 이미지에 텍스트가 있는지 하이브리드(휴리스틱 → 애매 시 Paddle)로 판별합니다.  
결과는 배치 폴더의 `image_text_check.csv`에 저장되며, `NO_TEXT` 이미지는 3단계 OCR에서 자동 스킵됩니다.

```cmd
docker compose run --rm ocr-parser python -m src.cli classify-images --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001
```

재검사:

```cmd
docker compose run --rm ocr-parser python -m src.cli classify-images --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001 --force
```

### 2.5단계 산출물

```text
datasets/discovery/{배치ID}/image_text_check.csv
```

## 3단계: OCR 및 최종 CSV

2단계에서 만든 **같은 배치**의 CSV를 `--manifest`로 지정합니다.  
2.5단계를 먼저 실행하면 `NO_TEXT` 이미지는 OCR을 건너뜁니다. 체크 파일이 없으면 경고 후 전부 OCR합니다.

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001
```

메모리 부담이 크면 청크로 나눕니다 (`NO_TEXT` 제외 후 기준):

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001 --offset 0 --limit 10

docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001 --offset 10 --limit 10
```

큰 이미지는 OCR 전에 긴 변 `OCR_MAX_IMAGE_SIDE`(기본 1600)로 축소합니다. `.env`에서 조절하고, `0`이면 리사이즈를 끕니다.

`.env`의 `BATCH_MEMBER`가 포함된 `batch_id` 행만 처리합니다.

DOM 값이 있으면 OCR 없이도 기록되고, 이미지가 있으면 OCR 후 DOM과 병합합니다.  
동일 상품·이미지 재실행 시 중복 행은 건너뜁니다.

### 3단계 산출물

```text
datasets/ocr_raw/{상품ID}_{이미지해시}.json
outcome/{BATCH_MEMBER}/{배치ID}/products.csv
outcome/{BATCH_MEMBER}/{배치ID}/failures.csv
```

예: `outcome/jaeseong/20260723-jaeseong-test-001/products.csv`

## 4단계: 팀 크롤 결과 (공유)

Console **4. 팀 결과**에서 `TEAM_MEMBERS`에 등록된 팀원들의 배치 진행
상태(발견·수집·판별·OCR·accepted 여부)를 한 화면에서 확인합니다.
읽기 전용이며 제출·Dagster 실행은 포함하지 않습니다.

## 5단계: 검증·제출·Dagster (플랫폼 관리자)

개인 `.env`에 `CONSOLE_PLATFORM_MODE=true`인 관리자만 Console **5. 플랫폼**
메뉴가 표시됩니다. 팀원 배치를 선택한 뒤 로컬 검증, accepted inbox 제출,
Dagster intake asset 실행을 순서대로 수행합니다.

```cmd
docker compose run --rm --no-deps normalizer python -m src.cli validate-collection --batch-id 20260724-jaeseong-001 --member jaeseong

docker compose run --rm --no-deps normalizer python -m src.cli submit-collection --batch-id 20260724-jaeseong-001 --member jaeseong
```

제출은 임시 디렉터리에서 검증한 뒤 원자적으로 확정합니다. 동일한 필수
산출물 묶음 checksum의 재제출은 성공으로 처리하고, 내용이 다른 동일 batch는
거부합니다. 기존 `datasets/discovery`와 `outcome` 원본은 변경하거나 삭제하지 않습니다.

```text
outcome/{BATCH_MEMBER}/{배치ID}/validation_report.json
datasets/inbox/accepted/{배치ID}/manifest.json
datasets/inbox/accepted/{배치ID}/discovery/
datasets/inbox/accepted/{배치ID}/outcome/
```

### Pipeline metadata 등록 (플랫폼 관리자)

팀원 Console에는 DB 기능을 노출하지 않습니다. 관리자는 accepted batch를
PostgreSQL의 전용 `pipeline_metadata` schema에 등록하고 조회할 수 있습니다.

```cmd
docker compose up -d postgres
docker compose run --rm normalizer python -m src.cli metadata-migrate
docker compose run --rm normalizer python -m src.cli metadata-register-submission --batch-id 20260724-jaeseong-001 --member jaeseong --code-version <git-sha>
docker compose run --rm normalizer python -m src.cli metadata-list-runs --batch-id 20260724-jaeseong-001
```

DB에는 파일 본문을 넣지 않고 경로, checksum, row count, byte size, version과
lineage만 저장합니다.

### Dagster 오케스트레이션 (플랫폼 관리자)

Dagster는 accepted batch와 애플리케이션 entrypoint를 연결하는 관리자용
오케스트레이션 계층입니다. 팀원 Console 흐름은 그대로 유지됩니다.

```cmd
docker compose --profile platform up -d dagster
```

관리자 UI는 기본값으로 [http://127.0.0.1:3000](http://127.0.0.1:3000)에서
열립니다. `accepted_collection_sensor`를 켜면 새 accepted batch를
`collection_batches` dynamic partition으로 등록하고 `process_collection_batch`
job을 실행합니다. 아직 구현 전인 Silver·MFDS·Reconciliation·Gold asset은
그래프 계약으로만 표시되며 materialize할 수 없습니다.

## 한 번에 보기 (예시)

```cmd
REM 1) 검색으로 최대 5개 발견
docker compose run --rm crawler python -m src.cli discover-search --keyword "육류" --batch-id 20260724-jaeseong-001 --max-products 5 --max-scrolls 3

REM 2) 상세 수집
docker compose run --rm crawler python -m src.cli collect-details --manifest /data/discovery/20260724-jaeseong-001/discovered_products.csv

REM 2.5) 이미지 텍스트 판별
docker compose run --rm ocr-parser python -m src.cli classify-images --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001

REM 3) OCR + 최종 CSV
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001

REM 4) 검증 + accepted inbox 제출
docker compose run --rm --no-deps normalizer python -m src.cli validate-collection --batch-id 20260724-jaeseong-001 --member jaeseong
docker compose run --rm --no-deps normalizer python -m src.cli submit-collection --batch-id 20260724-jaeseong-001 --member jaeseong
```

## 테스트

```cmd
docker compose run --rm crawler python -m compileall -q /app/src
docker compose run --rm crawler pytest -q /app/tests -m "not integration"

docker compose run --rm ocr-parser python -m compileall -q /app/src
docker compose run --rm ocr-parser pytest -q /app/tests -m "not integration"
```

로컬에서:

```cmd
python -m pytest -q tests -m "not integration"
```

## 종료

```cmd
docker compose down
```

`docker compose down -v`는 PostgreSQL 데이터까지 삭제하므로 일반 종료에 사용하지 않습니다.

## 주의사항

- 로그인·CAPTCHA·접근 제한 우회는 구현하지 않습니다.
- 무제한 카테고리/검색 순회는 하지 않습니다. `max-products` / `max-scrolls`로 제한하세요.
- 요청 사이에 `.env`의 `CRAWLER_REQUEST_INTERVAL_SECONDS` 대기가 적용됩니다.
- `product_name_preview`(발견 단계)는 카드 미리보기이며, 최종 상품명은 상세 수집 결과를 사용합니다.
- 각 팀원은 자기 `outcome/{팀원}/` 아래만 수정하고, 배치 ID를 겹치지 않게 사용합니다.
