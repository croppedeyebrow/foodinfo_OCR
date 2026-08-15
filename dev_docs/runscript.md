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

## (대안) 단계별 실행 UI

콘솔 앱은 Docker(`console` 서비스)로 실행합니다.  
호스트의 `python`/`python3`는 **런처용**일 뿐이고, Mac 권장은 셸 스크립트입니다.

```bash
# Mac / Linux (python 불필요)
bash start-console.sh
```

```cmd
REM Windows
start-console.cmd
```

| OS | 실행 |
|---|---|
| Windows | `start-console.cmd` |
| Mac | `bash start-console.sh` |

Python이 있을 때: Mac은 `python3 start_console.py`, Windows는 `python start_console.py`  
브라우저: http://127.0.0.1:8787

Docker Desktop이 꺼져 있으면 실행 여부를 묻고 엔진 준비까지 대기합니다 (`-y`로 생략 가능).

- 1 발견 → 2 상세 → 2.5 판별 → 3 OCR
- 실제 파이프라인은 console 컨테이너가 Docker로 crawler/ocr 호출 (동시 1잡)

---

## 1단계: 상품 발견 (Discovery)

아래 중 **하나만** 실행합니다.  
`--batch-id`는 매번 새 값을 쓰세요 (같은 배치 디렉터리가 있으면 거부됩니다).

### 1-A. URL 목록

입력: `datasets\input\product_urls.txt`

지원 URL 예:

```text
# 컬리 본사이트
https://www.kurly.com/goods/5047857?collectionCode=...

# 네이버플러스 스토어 컬리N마트
https://shopping.naver.com/window-products/kurlynmart/12274518551?...
```

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
datasets\discovery\{배치ID}\crawled_products.csv
```

배치마다 파일이 갈라지므로 팀원끼리 Git 충돌이 나지 않습니다.  
(예전 공용 `datasets\input\crawled_products.csv`는 더 이상 기본 경로가 아닙니다.)

---

## 2.5단계: 이미지 텍스트 판별 (권장)

상세 이미지에 텍스트가 있는지 판별해 `image_text_check.csv`를 만듭니다.  
`NO_TEXT`로 표시된 이미지는 3단계 OCR에서 자동으로 건너뜁니다.

```cmd
docker compose run --rm ocr-parser python -m src.cli classify-images --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001
```

이미 체크된 이미지는 기본 건너뜁니다. 재검사:

```cmd
docker compose run --rm ocr-parser python -m src.cli classify-images --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001 --force
```

### 2.5단계 결과

```text
datasets\discovery\{배치ID}\image_text_check.csv
```

---

## 3단계: OCR 및 최종 CSV

2단계에서 만든 **같은 배치**의 `crawled_products.csv`를 지정합니다.  
2.5단계를 먼저 실행해 두면 `NO_TEXT` 이미지는 OCR을 건너뜁니다.  
체크 파일이 없으면 경고 후 기존처럼 전부 OCR합니다.

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001
```

청크 실행 예:

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001 --offset 0 --limit 10
```

`.env`의 `BATCH_MEMBER`와 다른 팀원 배치는 자동으로 건너뜁니다.  
큰 이미지는 `OCR_MAX_IMAGE_SIDE`(기본 1600)로 줄여 OCR합니다. 기본값으로
`OCR_DISCLOSURE_GATE_ENABLED=true`이면 먼저 긴 변 640px
(`OCR_DISCLOSURE_GATE_MAX_IMAGE_SIDE`)의 저해상도 OCR에서 소비기한·유통기한·보관·
식품유형 키워드를 확인합니다. 상품명·브랜드 문구만 있는 이미지는 풀 OCR을 생략하고
게이트 OCR 원문만 `ocr_raw`에 남깁니다. 품질 비교가 필요하면
`OCR_DISCLOSURE_GATE_ENABLED=false`로 기존 풀 OCR 동작을 사용할 수 있습니다.

### 3단계 결과

```text
datasets\ocr_raw\
outcome\{BATCH_MEMBER}\{배치ID}\products.csv
outcome\{BATCH_MEMBER}\{배치ID}\failures.csv
```

---

## 4단계: 배치 검증 및 제출

Console의 **4. 검증·제출** 화면을 권장합니다. CLI로 실행할 때:

```cmd
docker compose run --rm --no-deps normalizer python -m src.cli validate-collection --batch-id 20260724-jaeseong-001 --member jaeseong

docker compose run --rm --no-deps normalizer python -m src.cli submit-collection --batch-id 20260724-jaeseong-001 --member jaeseong
```

필수 파일은 `discovered_products.csv`, `crawled_products.csv`,
`image_text_check.csv`, `products.csv`입니다. 검증 보고서는
`outcome\{BATCH_MEMBER}\{배치ID}\validation_report.json`, 접수 결과는
`datasets\inbox\accepted\{배치ID}\`에 생성됩니다.

같은 필수 산출물 묶음 checksum의 재제출은 멱등 성공하며, 다른 내용으로 이미
접수된 batch를 덮어쓰지 않습니다.

---

## 전체 예시 (검색 5건)

```cmd
docker compose run --rm crawler python -m src.cli discover-search --keyword "육류" --batch-id 20260724-jaeseong-001 --max-products 5 --max-scrolls 3

docker compose run --rm crawler python -m src.cli collect-details --manifest /data/discovery/20260724-jaeseong-001/discovered_products.csv

docker compose run --rm ocr-parser python -m src.cli classify-images --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001

docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/discovery/20260724-jaeseong-001/crawled_products.csv --batch-id 20260724-jaeseong-001

docker compose run --rm --no-deps normalizer python -m src.cli validate-collection --batch-id 20260724-jaeseong-001 --member jaeseong

docker compose run --rm --no-deps normalizer python -m src.cli submit-collection --batch-id 20260724-jaeseong-001 --member jaeseong
```
