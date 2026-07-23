# 컬리 상품 발견·상세 크롤링·OCR 파서

컬리 상품을 URL 목록·검색어·카테고리로 발견하고, 상세페이지 DOM·이미지를 수집한 뒤 PaddleOCR로 고시정보를 보완하여 팀원·배치별 CSV를 만드는 Docker 기반 프로젝트입니다.

## 구성

- `crawler`: Playwright 기반 상품 발견 및 상세페이지 수집
- `ocr-parser`: PaddleOCR 기반 OCR, DOM·OCR 병합, 최종 CSV
- `normalizer`: (추후) KFIA 기준 통합 정제
- `postgres`: (추후) 정제 데이터 적재

원본 이미지·크롤/OCR 원문 JSON은 `datasets`에 저장되며 Git에서 제외됩니다.  
발견 목록(`datasets/discovery/{배치ID}/`)과 최종 CSV(`outcome/{팀원}/{배치ID}/`)는 팀 공유용으로 남길 수 있습니다.

## 처리 흐름

```text
[URL 목록 / 검색어 / 카테고리]
  → 1) 상품 발견 → discovered_products.csv
  → 2) 상세페이지 수집 → crawl_raw JSON + detail_images + crawled_products.csv
  → 3) OCR·병합 → ocr_raw JSON + outcome/{팀원}/{배치ID}/products.csv
```

배치 ID 형식: `YYYYMMDD-팀원-일련번호` (예: `20260723-jaeseong-001`)

## 사전 준비

```cmd
cd /d C:\Dev\work_python\crowling_ocr_parser
docker compose build crawler
docker compose build ocr-parser
```

환경변수는 `.env`를 사용합니다. 예시:

```dotenv
BATCH_MEMBER=jaeseong
OUTCOME_ROOT=/outcome
CRAWLER_REQUEST_INTERVAL_SECONDS=2.0
CRAWLER_TIMEOUT_SECONDS=30
CRAWLER_MAX_RETRIES=3
CRAWLER_HEADLESS=true
PARSER_VERSION=0.2.0
```

컨테이너 상태 확인:

```cmd
docker compose run --rm crawler
docker compose run --rm ocr-parser
```

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
datasets/input/crawled_products.csv
outcome/{팀원}/{배치ID}/failures.csv   (상세 수집 실패 시)
```

### (호환) URL에서 바로 상세 수집

발견 단계 없이 URL 파일만으로 상세 수집할 때:

```cmd
docker compose run --rm crawler python -m src.cli collect-batch --input /data/input/product_urls.txt --batch-id 20260723-jaeseong-001
```

## 3단계: OCR 및 최종 CSV

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/input/crawled_products.csv
```

DOM 값이 있으면 OCR 없이도 기록되고, 이미지가 있으면 OCR 후 DOM과 병합합니다.  
동일 상품·이미지 재실행 시 중복 행은 건너뜁니다.

### 3단계 산출물

```text
datasets/ocr_raw/{상품ID}_{이미지해시}.json
outcome/{BATCH_MEMBER}/{배치ID}/products.csv
outcome/{BATCH_MEMBER}/{배치ID}/failures.csv
```

예: `outcome/jaeseong/20260723-jaeseong-test-001/products.csv`

## 한 번에 보기 (예시)

```cmd
REM 1) 검색으로 최대 5개 발견
docker compose run --rm crawler python -m src.cli discover-search --keyword "육류" --batch-id 20260724-jaeseong-001 --max-products 5 --max-scrolls 3

REM 2) 상세 수집
docker compose run --rm crawler python -m src.cli collect-details --manifest /data/discovery/20260724-jaeseong-001/discovered_products.csv

REM 3) OCR + 최종 CSV
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/input/crawled_products.csv
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
