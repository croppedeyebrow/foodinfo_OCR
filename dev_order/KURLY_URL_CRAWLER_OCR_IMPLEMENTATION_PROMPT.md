# 컬리 상품 URL 기반 상세페이지 크롤링·OCR 파싱 구현 지시서

## 1. AI IDE 작업 지시

현재 Docker 기반 Python 프로젝트에 **컬리 상품 URL을 입력받아 상품정보를 수집하고, 부족한 정보는 상세 이미지 OCR로 보완한 뒤, 상품별 원문 JSON과 팀원·배치별 CSV를 생성하는 기능**을 구현한다.

작업 대상 로컬 경로:

```text
C:\Dev\work_python\crowling_ocr_parser
```

기준 테스트 URL:

```text
https://www.kurly.com/goods/5047857?collectionCode=2607-vacanceonestop-home
```

입력 시작점은 JPEG 파일이 아니라 컬리 상품 URL이다.

---

## 2. 최종 목표

다음 명령으로 URL 목록을 처리할 수 있어야 한다.

```cmd
docker compose run --rm crawler python -m src.cli collect-batch --input /data/input/product_urls.txt --batch-id 20260719-jaeseong-001
```

크롤러 실행 결과:

```text
datasets/crawl_raw/{상품ID}.json
datasets/detail_images/{상품ID}_{이미지순번}_{해시}.jpg
datasets/input/crawled_products.csv
```

다음 명령으로 OCR 및 최종 CSV 생성을 수행한다.

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/input/crawled_products.csv
```

OCR 실행 결과:

```text
datasets/ocr_raw/{상품ID}_{이미지해시}.json
outcome/{팀원}/{배치ID}/products.csv
outcome/{팀원}/{배치ID}/failures.csv
```

---

## 3. 핵심 처리 원칙

필요한 값을 무조건 OCR로 추출하지 않는다.

우선순위:

```text
1. 상세페이지 DOM 텍스트
2. 상세페이지 구조화 데이터 또는 네트워크 응답
3. 상품고시정보·상세설명 이미지 OCR
4. 값이 없거나 충돌하면 검수 대상으로 분류
```

필드별 규칙:

| 상황 | 최종 처리 |
|---|---|
| DOM 값만 존재 | DOM 값 사용 |
| OCR 값만 존재 | OCR 값 사용 |
| DOM과 OCR의 의미가 동일 | DOM 원문 사용, `MATCHED` |
| DOM과 OCR이 충돌 | 자동 선택하지 않고 `REVIEW_REQUIRED` |
| 둘 다 값이 없음 | `FIELD_NOT_FOUND` |

컬리 판매 상품의 구체적 고시정보를 KFIA 참고값으로 덮어쓰지 않는다. KFIA 데이터와의 통합 정제는 이 프로젝트 다음 단계에서 수행한다.

---

## 4. 현재 프로젝트 구조

현재 프로젝트는 다음 Docker 서비스로 구성되어 있다.

```text
crawler       Playwright 기반 상세페이지 수집
ocr-parser    PaddleOCR 기반 이미지 OCR 및 고시정보 파싱
normalizer    추후 KFIA 기준 데이터와 통합 정제
postgres      추후 정제 데이터 적재
```

현재 주요 경로:

```text
apps/crawler/src/
apps/ocr-parser/src/
apps/normalizer/src/
contracts/
datasets/
outcome/
docker/
compose.yaml
.env
.env.example
```

기존 OCR 기능을 제거하지 말고 URL 수집 기능을 앞단에 추가한다.

---

## 5. 환경변수

기존 `.env`에는 다음 값이 설정되어 있다.

```dotenv
BATCH_MEMBER=jaeseong
OUTCOME_ROOT=/outcome
```

`.env.example`에는 특정 팀원이 아닌 예시 값을 둔다.

```dotenv
BATCH_MEMBER=member-name
OUTCOME_ROOT=/outcome
```

필요한 크롤러 설정:

```dotenv
CRAWLER_USER_AGENT=neulsom-kurly-ocr/0.1
CRAWLER_REQUEST_INTERVAL_SECONDS=2.0
CRAWLER_TIMEOUT_SECONDS=30
CRAWLER_MAX_RETRIES=3
CRAWLER_HEADLESS=true
```

환경변수를 코드에 하드코딩하지 않는다.

---

## 6. 디렉터리 변경

다음 디렉터리를 추가한다.

```text
datasets/
├─ input/
│  ├─ product_urls.txt
│  └─ crawled_products.csv
├─ crawl_raw/
├─ detail_images/
├─ images/
├─ html/
├─ ocr_raw/
└─ ocr_output/
```

Windows CMD 생성 명령:

```cmd
mkdir datasets\crawl_raw
mkdir datasets\detail_images
type nul > datasets\crawl_raw\.gitkeep
type nul > datasets\detail_images\.gitkeep
```

`.gitignore`에 추가한다.

```gitignore
datasets/crawl_raw/*
datasets/detail_images/*

!datasets/crawl_raw/.gitkeep
!datasets/detail_images/.gitkeep
```

원본 HTML, 다운로드 이미지, 크롤링 원문 JSON, OCR 원문 JSON은 Git에 커밋하지 않는다.

팀 공유 CSV는 `outcome` 아래에 저장하고 Git으로 공유한다.

---

## 7. Docker 볼륨

`compose.yaml`에서 `crawler`는 다음 볼륨을 사용해야 한다.

```yaml
crawler:
  volumes:
    - ./apps/crawler/src:/app/src
    - ./datasets:/data
```

`ocr-parser`는 다음 볼륨을 사용해야 한다.

```yaml
ocr-parser:
  volumes:
    - ./apps/ocr-parser/src:/app/src
    - ./contracts:/app/contracts:ro
    - ./datasets:/data
    - ./outcome:/outcome
```

Windows의 `outcome`은 컨테이너의 `/outcome`에 연결한다.

---

## 8. 입력 URL 파일

파일:

```text
datasets/input/product_urls.txt
```

형식:

```text
# 빈 줄과 #으로 시작하는 줄은 무시한다.
https://www.kurly.com/goods/5047857?collectionCode=2607-vacanceonestop-home
```

동일한 상품 ID가 여러 번 입력되면 한 번만 처리한다.

URL에서 상품 ID를 추출한다.

```text
입력 URL: https://www.kurly.com/goods/5047857?collectionCode=...
상품 ID: 5047857
정규 URL: https://www.kurly.com/goods/5047857
```

상품 ID를 추출할 수 없는 URL은 `INVALID_PRODUCT_URL` 실패로 기록한다.

---

## 9. 컬리 페이지에서 추출할 값

필수 추출 항목:

| 필드 | 설명 |
|---|---|
| `original_product_id` | URL의 상품 ID |
| `product_name_raw` | 컬리에 표시된 전체 상품명 |
| `product_url` | 쿼리스트링을 제거한 정규 URL |
| `food_name_candidate` | 브랜드·중량·보관표시를 제거한 식품명 후보 |
| `sales_unit_raw` | 판매단위 원문 |
| `weight_raw` | 중량·용량 원문 |
| `quantity_raw` | 개수·팩 수량 원문 |
| `expiration_info_dom` | 상세페이지 텍스트의 소비기한 원문 |
| `storage_method_dom` | 상세페이지 텍스트의 보관방법 원문 |
| `storage_type_dom` | `REFRIGERATED`, `FROZEN`, `ROOM_TEMPERATURE`, `UNKNOWN` |
| `detail_image_urls` | OCR 후보 상세 이미지 URL 배열 |
| `collected_at` | 수집 시각, ISO 8601, Asia/Seoul |

기준 URL에서 현재 확인되는 기대값 예시:

```text
original_product_id: 5047857
product_name_raw: [델리치오] 호주산 소고기 목초육 안심 스테이크 250g (냉장)
food_name_candidate: 소고기 안심 스테이크
sales_unit_raw: 1팩
weight_raw: 250g
quantity_raw: 2개입
expiration_info_dom: 수령일 포함 최소 3일 남은 제품을 보내 드립니다.
storage_method_dom: -2~10℃에서 즉시 냉장 보관하세요.
storage_type_dom: REFRIGERATED
```

사이트 내용은 변경될 수 있으므로 위 문자열 전체를 고정값으로 하드코딩하지 않는다.

---

## 10. 크롤링 방식

### 10.1 기본 방식

Playwright Chromium을 사용한다.

처리 순서:

1. 페이지 접근
2. DOM content loaded 대기
3. 상품 핵심 정보가 나타날 때까지 제한 시간 내 대기
4. 상품 상세정보 영역으로 스크롤
5. 필요한 경우 상세정보 탭 클릭
6. 지연 로딩 이미지가 로딩되도록 단계적으로 스크롤
7. 본문 텍스트 및 이미지 후보 수집
8. 원문 JSON 저장

### 10.2 선택자 규칙

- 실제 DOM을 확인하지 않고 임의의 CSS class를 하드코딩하지 않는다.
- 자동 생성되는 `css-xxxxx` 클래스만 단독 선택자로 사용하지 않는다.
- 우선 접근성 역할, 텍스트 레이블, `h1`, `img` 속성, 안정적인 `data-*` 속성을 사용한다.
- 선택자 후보를 여러 개 두고 순차적으로 시도한다.
- 선택자 실패 시 본문 텍스트에서 레이블 기반으로 값을 추출하는 fallback을 둔다.

### 10.3 요청 제한

- 기본적으로 상품을 순차 처리한다.
- 요청 사이에 환경변수의 대기시간을 적용한다.
- HTTP 오류와 타임아웃은 제한된 횟수만 재시도한다.
- 로그인, CAPTCHA, 접근제한을 우회하지 않는다.
- 스토어 전체를 무제한 자동 순회하지 않는다.

---

## 11. 크롤링 원문 JSON

파일 경로:

```text
datasets/crawl_raw/{상품ID}.json
```

Schema 예시:

```json
{
  "schema_version": "1.0",
  "batch_id": "20260719-jaeseong-001",
  "source_site": "KURLY",
  "original_product_id": "5047857",
  "product_url": "https://www.kurly.com/goods/5047857",
  "requested_url": "https://www.kurly.com/goods/5047857?collectionCode=2607-vacanceonestop-home",
  "product_name_raw": "[델리치오] 호주산 소고기 목초육 안심 스테이크 250g (냉장)",
  "food_name_candidate": "소고기 안심 스테이크",
  "sales_unit_raw": "1팩",
  "weight_raw": "250g",
  "quantity_raw": "2개입",
  "expiration_info_dom": "수령일 포함 최소 3일 남은 제품을 보내 드립니다.",
  "storage_method_dom": "-2~10℃에서 즉시 냉장 보관하세요.",
  "storage_type_dom": "REFRIGERATED",
  "detail_image_urls": [],
  "downloaded_images": [],
  "page_text": "상세페이지에서 수집한 전체 또는 필요한 범위의 텍스트",
  "collected_at": "2026-07-19T17:00:00+09:00",
  "crawl_status": "COMPLETED"
}
```

HTML 전체 저장은 디버그 옵션이 활성화됐을 때만 수행해도 된다.

---

## 12. 상세 이미지 후보 추출

모든 페이지 이미지를 OCR하지 않는다.

이미지 후보 판정 기준:

- 상품 상세설명 영역 내부 이미지
- 상품고시정보 또는 상세정보 주변 이미지
- 세로 길이가 길고 텍스트가 포함된 상세 이미지
- 대표 이미지, 아이콘, 배너, 후기 이미지, 추천 상품 이미지는 제외
- 동일 URL 또는 동일 SHA-256 이미지는 중복 처리하지 않음

초기 구현에서 정확한 고시 이미지 판별이 어렵다면 다음 방식으로 구현한다.

1. 상세정보 영역 이미지 후보를 모두 수집
2. URL, `alt`, `width`, `height`, DOM 위치를 원문 JSON에 기록
3. 이미지 다운로드
4. OCR 텍스트에 소비기한·유통기한·보관방법 키워드가 있는 이미지만 채택
5. 나머지는 `SKIPPED_NO_TARGET_FIELD` 처리

다운로드 파일명:

```text
{상품ID}_{순번}_{SHA256앞12자리}.jpg
```

저장 경로:

```text
datasets/detail_images/
```

---

## 13. 크롤러 출력 Manifest CSV

파일:

```text
datasets/input/crawled_products.csv
```

컬럼:

```csv
batch_id,original_product_id,product_name,product_url,image_path,source_image_url,source_site,expiration_info_dom,storage_method_dom,storage_type_dom,food_name_candidate,weight_raw,quantity_raw
```

상세 이미지가 여러 장이면 상품 ID는 같고 이미지 경로가 다른 여러 행을 생성할 수 있다.

DOM에서 필요한 값이 모두 확보되어 OCR이 불필요한 상품도 기록해야 한다. 이 경우 `image_path`와 `source_image_url`은 빈 값으로 둘 수 있도록 OCR 파이프라인을 수정한다.

---

## 14. OCR 원문 JSON

OCR 대상 이미지가 있을 때 상품·이미지별 JSON을 생성한다.

파일:

```text
datasets/ocr_raw/{상품ID}_{이미지SHA256앞12자리}.json
```

필수 항목:

```json
{
  "schema_version": "1.0",
  "batch_id": "20260719-jaeseong-001",
  "source_record_id": "KURLY:5047857:a93f8812b142",
  "source_site": "KURLY",
  "original_product_id": "5047857",
  "product_name": "상품명 원문",
  "product_url": "https://www.kurly.com/goods/5047857",
  "source_image_url": "상세 이미지 URL",
  "local_image_name": "5047857_01_a93f8812b142.jpg",
  "image_sha256": "전체 SHA-256",
  "ocr_engine": "PaddleOCR",
  "ocr_engine_version": "실제 버전",
  "ocr_confidence": 0.91,
  "ocr_raw_text": "OCR 전체 원문",
  "text_blocks": [],
  "collected_at": "2026-07-19T17:10:00+09:00"
}
```

OCR 원문 JSON에는 정제된 최종값을 덮어쓰지 않는다.

---

## 15. DOM·OCR 병합 규칙

병합 대상:

- 식품유형
- 소비기한·유통기한
- 보관방법
- 보관유형

최종 레코드는 각 필드의 출처를 함께 기록한다.

```text
DOM
OCR
DOM_AND_OCR
NOT_FOUND
```

소비기한 예시:

```text
DOM: 수령일 포함 최소 3일 남은 제품
OCR: 별도 표시일까지

결과:
expiration_info_raw = 수령일 포함 최소 3일 남은 제품
expiration_source = DOM
validation_status = REVIEW_REQUIRED
```

보관방법 예시:

```text
DOM: -2~10℃에서 즉시 냉장 보관
OCR: -2~10℃ 냉장보관

결과:
storage_method_raw = -2~10℃에서 즉시 냉장 보관
storage_source = DOM_AND_OCR
validation_status = MATCHED
```

문자열이 완전히 같을 때만 일치로 처리하지 말고 공백, 특수문자, `보관하세요` 같은 종결 표현을 제거한 비교 함수를 둔다.

---

## 16. 최종 products.csv

저장 위치:

```text
outcome/{BATCH_MEMBER}/{배치ID}/products.csv
```

예시:

```text
outcome/jaeseong/20260719-jaeseong-001/products.csv
```

필수 컬럼:

```csv
schema_version,batch_id,source_site,original_product_id,product_name_raw,food_name_candidate,product_url,sales_unit_raw,weight_raw,quantity_raw,food_type_raw,food_type_source,expiration_info_raw,expiration_source,storage_method_raw,storage_source,storage_type,ocr_confidence,crawl_collected_at,ocr_collected_at,parser_version,validation_status,parse_status
```

예시 행:

```csv
1.0,20260719-jaeseong-001,KURLY,5047857,[델리치오] 호주산 소고기 목초육 안심 스테이크 250g (냉장),소고기 안심 스테이크,https://www.kurly.com/goods/5047857,1팩,250g,2개입,포장육,OCR,수령일 포함 최소 3일 남은 제품,DOM,-2~10℃에서 즉시 냉장 보관,DOM_AND_OCR,REFRIGERATED,0.91,2026-07-19T17:00:00+09:00,2026-07-19T17:10:00+09:00,0.2.0,MATCHED,COMPLETED
```

CSV 저장 규칙:

- 인코딩: `UTF-8-SIG`
- Python `csv.DictWriter` 사용
- `newline=""` 사용
- 컬럼 순서 고정
- 날짜·시각은 ISO 8601
- 빈 값은 빈 문자열
- Excel 수동 저장을 파이프라인 입력으로 사용하지 않음

---

## 17. 팀원·배치 관리

팀원 디렉터리:

```text
outcome/
├─ jaeseong/
├─ sunyeong/
└─ woohee/
```

배치 ID 형식:

```text
YYYYMMDD-팀원-일련번호
```

예시:

```text
20260719-jaeseong-001
20260719-sunyeong-001
20260719-woohee-001
```

각 팀원은 자기 디렉터리만 수정한다. 기존 배치 CSV를 덮어쓰지 않고 새 배치를 생성한다.

---

## 18. 실패 처리

저장 위치:

```text
outcome/{팀원}/{배치ID}/failures.csv
```

오류 코드:

```text
INVALID_PRODUCT_URL
PAGE_FETCH_FAILED
PAGE_TIMEOUT
PRODUCT_ID_NOT_FOUND
PRODUCT_NAME_NOT_FOUND
DETAIL_SECTION_NOT_FOUND
DETAIL_IMAGE_NOT_FOUND
IMAGE_DOWNLOAD_FAILED
IMAGE_FORMAT_UNSUPPORTED
OCR_FAILED
OCR_TEXT_EMPTY
FIELD_PARSE_FAILED
DOM_OCR_CONFLICT
SCHEMA_VALIDATION_FAILED
```

`FIELD_PARSE_FAILED`나 `DOM_OCR_CONFLICT`가 발생하더라도 수집한 DOM 원문과 OCR 원문은 삭제하지 않는다.

---

## 19. 권장 모듈 구조

```text
apps/crawler/src/
├─ __init__.py
├─ cli.py
├─ config.py
├─ models.py
├─ url_parser.py
├─ kurly_page.py
├─ field_extractor.py
├─ image_candidate.py
├─ image_downloader.py
├─ checksum.py
├─ raw_exporter.py
└─ manifest_exporter.py

apps/ocr-parser/src/
├─ __init__.py
├─ cli.py
├─ models.py
├─ ocr_engine.py
├─ disclosure_parser.py
├─ merge_policy.py
├─ checksum.py
├─ exporter.py
└─ pipeline.py
```

책임을 한 파일에 몰아넣지 않는다.

---

## 20. 데이터 모델 요구사항

Pydantic 모델을 사용하여 다음 모델을 정의한다.

```text
KurlyProductUrl
CrawledProductRecord
DownloadedImage
CrawlFailureRecord
RawOcrRecord
ParsedDisclosureFields
MergedProductRecord
OcrFailureRecord
```

HTTP URL 필드는 `HttpUrl` 또는 명시적인 검증 함수를 사용한다.

CSV의 빈 선택 필드는 Pydantic 검증 전에 빈 문자열을 `None`으로 변환한다.

---

## 21. 중복 처리

중복 기준:

```text
상품 중복: source_site + original_product_id
이미지 중복: SHA-256
레코드 중복: source_site + original_product_id + image_sha256
```

같은 상품과 같은 이미지가 재처리되면 CSV에 동일 레코드를 계속 추가하지 않는다.

다음 중 하나를 구현한다.

1. 기존 CSV의 `source_record_id`를 읽어 중복 행 건너뛰기
2. 배치 시작 시 메모리에 기존 키 집합 구성

MVP에서는 2번으로 충분하다.

---

## 22. 테스트 요구사항

외부 컬리 페이지에 의존하는 테스트와 순수 단위 테스트를 분리한다.

필수 단위 테스트:

```text
test_parse_kurly_product_id
test_canonicalize_kurly_url
test_extract_labeled_text
test_normalize_storage_type
test_select_dom_value_when_ocr_missing
test_select_ocr_value_when_dom_missing
test_mark_review_when_dom_and_ocr_conflict
test_write_raw_json
test_write_utf8_sig_csv
test_skip_duplicate_source_record
```

HTML fixture 기반 테스트:

```text
tests/fixtures/kurly_product_5047857.html
```

실페이지 테스트는 별도 표시를 붙인다.

```python
@pytest.mark.integration
```

기본 테스트 실행 시 실페이지에 요청하지 않는다.

---

## 23. 실행 명령

### 23.1 Compose 확인

```cmd
docker compose config
```

### 23.2 크롤러 빌드

```cmd
docker compose build crawler
```

### 23.3 URL 수집

```cmd
docker compose run --rm crawler python -m src.cli collect-batch --input /data/input/product_urls.txt --batch-id 20260719-jaeseong-001
```

### 23.4 OCR 이미지 빌드

```cmd
docker compose build ocr-parser
```

### 23.5 OCR 및 CSV 생성

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/input/crawled_products.csv
```

### 23.6 문법 검사

```cmd
docker compose run --rm crawler python -m compileall -q /app/src
docker compose run --rm ocr-parser python -m compileall -q /app/src
```

### 23.7 테스트

Compose에 다음 테스트 볼륨을 추가한다.

```yaml
- ./tests:/app/tests:ro
```

실행:

```cmd
docker compose run --rm crawler pytest -q /app/tests -m "not integration"
docker compose run --rm ocr-parser pytest -q /app/tests -m "not integration"
```

---

## 24. 구현 완료 조건

기준 URL 한 개로 다음 조건을 모두 만족해야 한다.

- [ ] URL에서 상품 ID `5047857` 추출
- [ ] 쿼리스트링을 제거한 정규 URL 생성
- [ ] 상품명 추출
- [ ] 판매단위·중량·수량 중 확인 가능한 값 추출
- [ ] DOM 소비기한 원문 추출
- [ ] DOM 보관방법 원문 추출
- [ ] 보관유형 `REFRIGERATED` 판정
- [ ] `datasets/crawl_raw/5047857.json` 생성
- [ ] OCR 후보 이미지 URL 기록
- [ ] 필요한 이미지 다운로드 및 SHA-256 생성
- [ ] OCR 대상이 있으면 상품·이미지별 원문 JSON 생성
- [ ] `outcome/jaeseong/{배치ID}/products.csv` 생성
- [ ] CSV가 UTF-8-SIG로 저장됨
- [ ] 실패 시 `failures.csv`에 오류 코드 기록
- [ ] 동일 상품·이미지 재실행 시 중복 행을 생성하지 않음
- [ ] 단위 테스트 통과

---

## 25. MVP 범위에서 제외

다음 기능은 이번 구현에 포함하지 않는다.

- 컬리 전체 상품 자동 순회
- 무제한 병렬 크롤링
- 로그인 또는 CAPTCHA 우회
- 프록시 회전
- 관리자 검수 UI
- KFIA CSV와 최종 매칭
- PostgreSQL 최종 적재
- 클라우드 이미지 저장소
- GPU OCR

---

## 26. AI IDE 응답 형식

AI IDE는 구현 전에 다음 내용을 먼저 제시한다.

1. 현재 프로젝트에서 변경할 파일 목록
2. 새로 추가할 파일 목록
3. 기존 OCR 코드와의 호환 방식
4. 구현 순서

그다음 코드를 수정하고 다음 결과를 보고한다.

1. 구현한 기능 요약
2. 실행한 테스트와 결과
3. 실제 컬리 페이지 테스트 여부
4. 생성된 샘플 JSON·CSV 경로
5. 남아 있는 제약이나 실패 항목

기존 사용자 변경사항을 임의로 삭제하거나 전체 파일을 불필요하게 교체하지 않는다.

