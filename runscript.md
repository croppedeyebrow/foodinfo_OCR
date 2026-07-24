# 실행 스크립트 (명령어 모음)

프로젝트 루트에서 실행합니다.

```cmd
cd /d C:\Dev\work_python\crowling_ocr_parser
```

배치 ID 예: `YYYYMMDD-팀원-일련번호`  
팀원: `jaeseong` / `sunyeong` / `woohee`  
`.env`의 `BATCH_MEMBER`와 `--batch-id`의 팀원 이름을 맞춥니다.

---

## 0. 최초 준비 (한 번)

```cmd
copy .env.example .env
```

`.env`에서 `BATCH_MEMBER`를 본인 이름으로 수정합니다.

```cmd
docker compose build crawler
docker compose build ocr-parser
```

---

## 1단계: 상품 발견 (Discovery)

아래 중 **하나만** 실행합니다.  
`--batch-id`는 매번 새 값을 쓰세요 (같은 배치 디렉터리가 있으면 거부됩니다).

### 1-A. URL 목록

입력: `datasets\input\product_urls.txt`

```cmd
docker compose run --rm crawler python -m src.cli discover-urls --input /data/input/product_urls.txt --batch-id 20260724-jaeseong-001
```

### 1-B. 검색어

```cmd
docker compose run --rm crawler python -m src.cli discover-search --keyword "육류" --batch-id 20260724-jaeseong-002 --max-products 5 --max-scrolls 3
```

### 1-C. 카테고리

`--category-code` 또는 `--category-url` 중 **하나만** 사용합니다.

```cmd
docker compose run --rm crawler python -m src.cli discover-category --category-code 910 --batch-id 20260724-jaeseong-003 --max-products 5 --max-scrolls 3
```

```cmd
docker compose run --rm crawler python -m src.cli discover-category --category-url "https://www.kurly.com/categories/910" --batch-id 20260724-jaeseong-003 --max-products 5 --max-scrolls 3
```

### 1단계 결과

```text
datasets\discovery\{배치ID}\discovered_products.csv
datasets\discovery\{배치ID}\manifest.json
```

---

## 2단계: 상세페이지 수집

1단계에서 만든 `discovered_products.csv` 경로의 배치 ID를 그대로 넣습니다.

```cmd
docker compose run --rm crawler python -m src.cli collect-details --manifest /data/discovery/20260724-jaeseong-002/discovered_products.csv
```

이미 수집한 상품을 다시 받을 때:

```cmd
docker compose run --rm crawler python -m src.cli collect-details --manifest /data/discovery/20260724-jaeseong-002/discovered_products.csv --force
```

### (호환) URL에서 바로 상세 수집

발견 단계 없이 URL 파일만으로 상세 수집:

```cmd
docker compose run --rm crawler python -m src.cli collect-batch --input /data/input/product_urls.txt --batch-id 20260724-jaeseong-001
```

### 2단계 결과

```text
datasets\crawl_raw\{상품ID}.json
datasets\detail_images\
datasets\input\crawled_products.csv
```

---

## 3단계: OCR 및 최종 CSV

`.env`의 `BATCH_MEMBER`에 해당하는 배치만 처리합니다.  
다른 팀원 배치는 자동으로 건너뜁니다.

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/input/crawled_products.csv
```

특정 배치만 지정:

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/input/crawled_products.csv --batch-id 20260724-jaeseong-001
```

`--batch-id`는 반드시 본인 `BATCH_MEMBER`가 들어간 배치여야 합니다.

### 3단계 결과

```text
datasets\ocr_raw\
outcome\{BATCH_MEMBER}\{배치ID}\products.csv
outcome\{BATCH_MEMBER}\{배치ID}\failures.csv
```

---

## 전체 예시 (검색 5건)

```cmd
docker compose run --rm crawler python -m src.cli discover-search --keyword "육류" --batch-id 20260724-jaeseong-001 --max-products 5 --max-scrolls 3

docker compose run --rm crawler python -m src.cli collect-details --manifest /data/discovery/20260724-jaeseong-001/discovered_products.csv

docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/input/crawled_products.csv --batch-id 20260724-jaeseong-001
```
