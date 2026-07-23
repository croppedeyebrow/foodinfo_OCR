컬리 상품 발견(Discovery) 기능 확장 구현 지시서

0. AI IDE에 전달할 최상위 명령

현재 프로젝트의 기존 상세페이지 수집 및 OCR 기능을 보존하면서, 상품 수집 시작점을 다음 세 가지 모드로 확장한다.

사용자가 직접 입력한 상품 URL 목록

컬리 검색어 결과

컬리 카테고리 결과

검색·카테고리 페이지에서는 상품 상세정보와 OCR을 즉시 처리하지 말고, 먼저 상품 ID와 상세 URL을 발견하여 discovered_products.csv로 저장한다. 이후 기존 상세페이지 수집 파이프라인이 이 CSV를 입력받도록 연결한다.

기존 사용자 변경사항을 임의로 삭제하거나 전체 파일을 불필요하게 교체하지 않는다. 구현 전에 현재 파일 구조와 변경사항을 확인하고, 변경·추가할 파일 목록 및 구현 순서를 먼저 보고한 후 작업한다.

1. 프로젝트 배경

프로젝트 로컬 경로:

C:\Dev\work_python\crowling_ocr_parser

기존 프로젝트의 목적:

컬리 상품 상세페이지
→ DOM 정보 수집
→ 상세 이미지 다운로드
→ PaddleOCR
→ 상품별 원문 JSON
→ 팀원·배치별 정형 CSV

현재 입력 방식:

datasets/input/product_urls.txt

현재 방식은 사용자가 이미 알고 있는 상품 URL만 수집할 수 있다. 이를 검색어와 카테고리 기반 상품 발견까지 확장한다.

2. 구현 목표

다음 네 개의 CLI 명령을 지원한다.

discover-urls
discover-search
discover-category
collect-details

역할:

명령

역할

discover-urls

사용자가 작성한 상품 URL 목록 검증·정규화

discover-search

컬리 검색 결과에서 상품 URL 발견

discover-category

컬리 카테고리에서 상품 URL 발견

collect-details

발견 결과 CSV를 읽어 각 상품 상세페이지 수집

전체 실행 흐름:

[URL 목록 / 검색어 / 카테고리]
→ 상품 발견
→ discovered_products.csv
→ 상세페이지 수집
→ crawl_raw JSON + 상세 이미지
→ OCR
→ 상품별 OCR JSON
→ outcome/{팀원}/{배치ID}/products.csv

3. 수집 모드

3.1 URL 목록 모드

입력 파일:

datasets/input/product_urls.txt

예시:

# 빈 줄과 주석은 무시한다.

https://www.kurly.com/goods/5047857?collectionCode=2607-vacanceonestop-home
https://www.kurly.com/goods/1234567

실행 예시:

docker compose run --rm crawler python -m src.cli discover-urls ^
--input /data/input/product_urls.txt ^
--batch-id 20260723-jaeseong-001

3.2 검색어 모드

2026-07-23 기준 컬리 검색 URL 형태:

https://www.kurly.com/search?sword={URL 인코딩된 검색어}

예시:

https://www.kurly.com/search?sword=육류
https://www.kurly.com/search?sword=돼지고기

코드에서는 반드시 URL 인코딩한다.

from urllib.parse import quote

search_url = f"https://www.kurly.com/search?sword={quote(keyword)}"

실행 예시:

docker compose run --rm crawler python -m src.cli discover-search ^
--keyword "육류" ^
--batch-id 20260723-jaeseong-002 ^
--max-products 20 ^
--max-scrolls 10

특정 제품 검색 예시:

docker compose run --rm crawler python -m src.cli discover-search ^
--keyword "서울우유 저지방" ^
--batch-id 20260723-jaeseong-003 ^
--max-products 20 ^
--max-scrolls 10

3.3 카테고리 모드

2026-07-23 기준 컬리 카테고리 URL 형태:

https://www.kurly.com/categories/{category_code}

정육·가공육·달걀 카테고리 예시:

https://www.kurly.com/categories/910

실행 예시:

docker compose run --rm crawler python -m src.cli discover-category ^
--category-code 910 ^
--batch-id 20260723-jaeseong-004 ^
--max-products 50 ^
--max-scrolls 20

URL을 직접 받는 방식도 지원한다.

docker compose run --rm crawler python -m src.cli discover-category ^
--category-url "https://www.kurly.com/categories/910" ^
--batch-id 20260723-jaeseong-004 ^
--max-products 50 ^
--max-scrolls 20

--category-code와 --category-url은 동시에 사용할 수 없으며 둘 중 하나는 필수다.

4. 검색과 카테고리 의미 구분

검색어 육류와 컬리 카테고리 910은 같은 의미가 아니다.

방식

의미

SEARCH: 육류

컬리 검색 인덱스에서 육류와 관련된 상품

CATEGORY: 910

컬리가 정육·가공육·달걀 카테고리로 분류한 상품

구현 시 두 방식을 하나의 함수로 억지로 합치지 말고, 공통 발견 엔진 위에 별도 진입점을 둔다.

SearchProductDiscovery
CategoryProductDiscovery
UrlListProductDiscovery

검색과 카테고리 양쪽에서 같은 상품이 발견될 수 있으므로 상품 ID 기준 중복 제거가 필요하다.

5. Discovery와 상세 수집 분리

카테고리나 검색 결과에서 상품을 찾는 즉시 상세페이지 OCR까지 실행하지 않는다.

1단계:

검색·카테고리 페이지
→ 상품 카드 탐색
→ 상품 ID 및 URL 수집
→ discovered_products.csv

2단계:

discovered_products.csv
→ 상품 상세페이지 순차 접근
→ DOM 추출
→ 이미지 다운로드
→ crawled_products.csv

3단계:

crawled_products.csv
→ OCR
→ JSON
→ outcome CSV

분리 이유:

발견된 상품 목록을 사람이 먼저 확인할 수 있음

상세 수집 도중 실패해도 발견 작업을 다시 하지 않음

중단 후 이어서 실행 가능

팀원 간 상품 배치 분할 가능

검색·카테고리 페이지와 상세페이지 장애를 분리할 수 있음

6. 디렉터리 구조

다음 구조를 사용한다.

datasets/
├─ input/
│ └─ product_urls.txt
│
├─ discovery/
│ └─ {배치ID}/
│ ├─ discovered_products.csv
│ ├─ discovery_failures.csv
│ └─ manifest.json
│
├─ crawl_raw/
├─ detail_images/
├─ html/
├─ ocr_raw/
└─ input/
└─ crawled_products.csv

outcome/
├─ jaeseong/
├─ sunyeong/
└─ woohee/

필요한 디렉터리 생성:

mkdir datasets\discovery
type nul > datasets\discovery\.gitkeep

팀원 간 발견 목록을 공유할 예정이면 datasets/discovery의 CSV와 manifest를 Git에 포함한다. 대용량 HTML·이미지·원문 JSON은 계속 Git에서 제외한다.

7. 상품 링크 탐색 규칙

검색·카테고리 페이지에서 다음 형태의 링크를 찾는다.

/goods/5047857
https://www.kurly.com/goods/5047857
https://www.kurly.com/goods/5047857?collectionCode=...

상품 경로 정규식:

import re

PRODUCT_PATH_PATTERN = re.compile(r"/goods/(?P<product_id>\d+)")

상품 URL 정규화 함수:

def canonicalize_product_url(href: str) -> tuple[str, str] | None:
match = PRODUCT_PATH_PATTERN.search(href)
if match is None:
return None

    product_id = match.group("product_id")
    canonical_url = f"https://www.kurly.com/goods/{product_id}"
    return product_id, canonical_url

다음 값은 모두 동일한 상품으로 처리한다.

https://www.kurly.com/goods/5047857
https://www.kurly.com/goods/5047857?collectionCode=2607-vacanceonestop-home
/goods/5047857

중복 키:

source_site + original_product_id

MVP에서는 original_product_id만으로도 중복 제거할 수 있지만, 데이터 모델에는 source_site를 유지한다.

8. Playwright 상품 카드 탐색

자동 생성 CSS 클래스만 단독 선택자로 사용하지 않는다.

우선 선택자:

page.locator("a[href*='/goods/']")

각 링크에서 수집할 후보:

href

상품 카드 내부 텍스트

상품 카드 이미지의 alt

현재 발견 순서

상품명 미리보기 추출 우선순위:

링크 내부의 의미 있는 텍스트

카드 내부 이미지 alt

값이 없으면 빈 문자열

상품명 미리보기는 상세페이지에서 얻는 최종 상품명이 아니므로 발견 실패 기준으로 사용하지 않는다.

9. 무한 스크롤 및 지연 로딩

검색·카테고리 페이지의 상품이 지연 로딩될 수 있으므로 단계적으로 스크롤한다.

필수 종료 조건:

max_products 도달

max_scrolls 도달

연속 3회 신규 상품 없음

페이지 오류

전체 작업 타임아웃

의사 코드:

known_products: dict[str, DiscoveredProduct] = {}
unchanged_rounds = 0

for scroll_index in range(max_scrolls):
collect_visible_product_links(known_products)

    before_count = len(known_products)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(scroll_wait_ms)

    collect_visible_product_links(known_products)

    if len(known_products) == before_count:
        unchanged_rounds += 1
    else:
        unchanged_rounds = 0

    if len(known_products) >= max_products:
        break

    if unchanged_rounds >= 3:
        break

최종 결과는 발견 순서를 유지하면서 max_products까지만 저장한다.

개발 기본값:

max_products = 20
max_scrolls = 10
scroll_wait_ms = 1500

무제한 수집 옵션을 만들지 않는다.

10. Discovery 출력 CSV

파일:

datasets/discovery/{배치ID}/discovered_products.csv

컬럼 순서:

schema_version,batch_id,source_site,source_mode,source_value,original_product_id,product_name_preview,product_url,discovery_order,discovered_at,discovery_status

카테고리 수집 예시:

1.0,20260723-jaeseong-004,KURLY,CATEGORY,910,5047857,[델리치오] 호주산 소고기 목초육 안심 스테이크 250g,https://www.kurly.com/goods/5047857,1,2026-07-23T22:00:00+09:00,DISCOVERED

검색 수집 예시:

1.0,20260723-jaeseong-002,KURLY,SEARCH,육류,5047857,[델리치오] 호주산 소고기 목초육 안심 스테이크 250g,https://www.kurly.com/goods/5047857,1,2026-07-23T22:00:00+09:00,DISCOVERED

URL 목록 예시:

1.0,20260723-jaeseong-001,KURLY,URL_LIST,product_urls.txt,5047857,,https://www.kurly.com/goods/5047857,1,2026-07-23T22:00:00+09:00,DISCOVERED

CSV 저장 규칙:

UTF-8-SIG

newline=""

csv.DictWriter

컬럼 순서 고정

ISO 8601, Asia/Seoul

동일 상품 ID 중복 행 금지

11. Discovery manifest

파일:

datasets/discovery/{배치ID}/manifest.json

예시:

{
"schema_version": "1.0",
"batch_id": "20260723-jaeseong-004",
"source_site": "KURLY",
"source_mode": "CATEGORY",
"source_value": "910",
"requested_url": "https://www.kurly.com/categories/910",
"max_products": 50,
"max_scrolls": 20,
"discovered_count": 50,
"duplicate_count": 3,
"started_at": "2026-07-23T21:59:00+09:00",
"finished_at": "2026-07-23T22:01:00+09:00",
"status": "COMPLETED"
}

상태:

RUNNING
COMPLETED
PARTIAL_FAILED
FAILED

12. 발견 출처 복수 기록

동일한 상품이 검색과 카테고리 양쪽에서 발견될 수 있다.

한 배치 내부에서는 상품 ID별 한 행만 유지한다.

여러 배치의 결과를 통합할 때는 발견 출처를 보존한다.

개념 모델:

{
"original_product_id": "5047857",
"product_url": "https://www.kurly.com/goods/5047857",
"discovery_sources": [
{
"mode": "SEARCH",
"value": "육류"
},
{
"mode": "CATEGORY",
"value": "910"
}
]
}

MVP의 개별 CSV에서는 한 행에 현재 배치의 source_mode, source_value만 기록해도 된다.

13. 상세페이지 수집 연결

발견 완료 후 다음 명령으로 상세페이지를 처리한다.

docker compose run --rm crawler python -m src.cli collect-details ^
--manifest /data/discovery/20260723-jaeseong-004/discovered_products.csv

collect-details가 CSV에서 읽을 필수 컬럼:

batch_id
source_site
original_product_id
product_url

상세 수집 결과:

datasets/crawl*raw/{상품ID}.json
datasets/detail_images/{상품ID}*{순번}\_{해시}.jpg
datasets/input/crawled_products.csv

이미 상세 수집을 완료한 상품은 기본적으로 건너뛴다.

재수집 옵션:

--force

--force가 없으면 기존 성공 결과를 덮어쓰지 않는다.

14. OCR 연결

상세 수집 완료 후 기존 OCR 파이프라인을 사용한다.

docker compose run --rm ocr-parser python -m src.cli process-batch ^
--manifest /data/input/crawled_products.csv

최종 결과:

datasets/ocr*raw/{상품ID}*{이미지해시}.json
outcome/{BATCH_MEMBER}/{배치ID}/products.csv
outcome/{BATCH_MEMBER}/{배치ID}/failures.csv

Discovery 기능을 구현하면서 기존 OCR JSON 및 outcome 경로 규칙을 변경하지 않는다.

15. CLI 요구사항

15.1 URL 목록

@app.command("discover-urls")
def discover_urls(
input_file: Path = typer.Option(..., "--input", exists=True),
batch_id: str = typer.Option(..., "--batch-id"),
) -> None:
...

15.2 검색

@app.command("discover-search")
def discover_search(
keyword: str = typer.Option(..., "--keyword"),
batch_id: str = typer.Option(..., "--batch-id"),
max_products: int = typer.Option(20, "--max-products", min=1, max=500),
max_scrolls: int = typer.Option(10, "--max-scrolls", min=1, max=100),
) -> None:
...

15.3 카테고리

@app.command("discover-category")
def discover_category(
batch_id: str = typer.Option(..., "--batch-id"),
category_code: str | None = typer.Option(None, "--category-code"),
category_url: str | None = typer.Option(None, "--category-url"),
max_products: int = typer.Option(20, "--max-products", min=1, max=500),
max_scrolls: int = typer.Option(10, "--max-scrolls", min=1, max=100),
) -> None:
...

카테고리 입력 검증:

if bool(category_code) == bool(category_url):
raise typer.BadParameter(
"--category-code 또는 --category-url 중 하나만 입력해야 합니다."
)

15.4 상세 수집

@app.command("collect-details")
def collect_details(
manifest: Path = typer.Option(..., "--manifest", exists=True),
force: bool = typer.Option(False, "--force"),
) -> None:
...

16. 권장 모듈 구조

기존 파일을 확인한 뒤 다음 책임 단위로 구성한다.

apps/crawler/src/
├─ **init**.py
├─ cli.py
├─ config.py
├─ models.py
├─ url_parser.py
├─ discovery/
│ ├─ **init**.py
│ ├─ base.py
│ ├─ url_list.py
│ ├─ search.py
│ ├─ category.py
│ ├─ page_scroller.py
│ └─ link_extractor.py
├─ exporter/
│ ├─ **init**.py
│ ├─ discovery_csv.py
│ ├─ discovery_manifest.py
│ └─ failure_csv.py
└─ detail/
└─ 기존 상세페이지 수집 모듈

규모가 작다면 하위 디렉터리를 줄일 수 있지만 다음 책임은 분리한다.

URL 검증·정규화

Playwright 페이지 탐색

상품 링크 추출

스크롤 종료 판단

중복 제거

CSV·manifest 저장

실패 기록

17. 데이터 모델

Pydantic 모델을 사용한다.

class DiscoveryMode(str, Enum):
URL_LIST = "URL_LIST"
SEARCH = "SEARCH"
CATEGORY = "CATEGORY"

class DiscoveredProduct(BaseModel):
schema_version: str = "1.0"
batch_id: str
source_site: str = "KURLY"
source_mode: DiscoveryMode
source_value: str
original_product_id: str
product_name_preview: str | None = None
product_url: HttpUrl
discovery_order: int
discovered_at: datetime
discovery_status: str = "DISCOVERED"

class DiscoveryFailure(BaseModel):
batch_id: str
source_mode: DiscoveryMode
source_value: str
requested_url: str
error_code: str
error_message: str
failed_at: datetime

18. 오류 코드

INVALID_PRODUCT_URL
INVALID_CATEGORY_URL
INVALID_CATEGORY_CODE
EMPTY_SEARCH_KEYWORD
DISCOVERY_PAGE_FETCH_FAILED
DISCOVERY_PAGE_TIMEOUT
PRODUCT_LINK_NOT_FOUND
PRODUCT_ID_NOT_FOUND
SCROLL_LIMIT_REACHED
MAX_PRODUCTS_REACHED
DISCOVERY_EXPORT_FAILED
DISCOVERY_PARTIAL_FAILED

SCROLL_LIMIT_REACHED와 MAX_PRODUCTS_REACHED는 작업 실패가 아니라 종료 사유로 manifest에 기록할 수 있다.

페이지 중간 오류가 발생하더라도 이미 발견한 상품이 있으면 CSV를 저장하고 PARTIAL_FAILED로 처리한다.

19. 재시도·요청 제한

기존 환경변수를 사용한다.

CRAWLER_REQUEST_INTERVAL_SECONDS=2.0
CRAWLER_TIMEOUT_SECONDS=30
CRAWLER_MAX_RETRIES=3
CRAWLER_HEADLESS=true

정책:

요청은 기본적으로 순차 실행

페이지 간 최소 대기시간 적용

동일 요청 무한 재시도 금지

로그인, CAPTCHA, 접근 제한 우회 금지

프록시 회전 구현 금지

무제한 카테고리 전체 수집 금지

개발 중 기본 수집량은 5건

사이트 이용정책과 접근 제한을 준수하고 서버 부하를 최소화한다.

20. 중단 후 재개

상세 수집은 다음 기준으로 재개 가능해야 한다.

발견됨 + crawl_raw 없음 → 처리
발견됨 + crawl_raw 성공 존재 → 건너뜀
발견됨 + 이전 실패 존재 → 재시도 정책에 따라 처리
--force 지정 → 기존 결과와 관계없이 재수집

Discovery 자체를 재실행할 때 같은 배치 CSV가 존재하면 다음 중 안전한 정책을 선택한다.

권장 MVP 정책:

동일 batch_id 출력 디렉터리가 이미 존재하면 실행 거부

사용자가 새 배치 ID를 만들도록 명확한 오류를 출력한다.

기존 CSV에 조용히 덧붙이거나 덮어쓰지 않는다.

21. 팀 협업 규칙

배치 ID:

YYYYMMDD-팀원-일련번호

예시:

20260723-jaeseong-001
20260723-sunyeong-001
20260723-woohee-001

각 팀원은 다음 경로만 수정한다.

outcome/jaeseong/
outcome/sunyeong/
outcome/woohee/

Discovery CSV는 배치 ID가 다르면 충돌하지 않는다.

같은 배치 ID를 여러 팀원이 사용하지 않는다.

22. 단위 테스트

외부 사이트에 접속하지 않는 테스트를 우선 작성한다.

필수 테스트:

test_extract_product_id_from_absolute_url
test_extract_product_id_from_relative_url
test_remove_query_string_from_product_url
test_reject_non_kurly_product_url
test_encode_korean_search_keyword
test_build_category_url
test_validate_category_code_or_url_exclusive
test_deduplicate_products_by_id
test_preserve_discovery_order
test_stop_when_max_products_reached
test_stop_after_three_unchanged_scrolls
test_write_discovery_csv_with_utf8_sig
test_reject_existing_batch_directory

HTML fixture 테스트:

tests/fixtures/kurly_search_result.html
tests/fixtures/kurly_category_910.html

실제 컬리 페이지 테스트에는 integration 표시를 붙인다.

@pytest.mark.integration

기본 테스트에서는 실제 컬리 페이지로 요청하지 않는다.

23. 테스트 실행 명령

Compose의 crawler 볼륨에 테스트 디렉터리를 추가한다.

- ./tests:/app/tests:ro

문법 검사:

docker compose run --rm crawler python -m compileall -q /app/src

단위 테스트:

docker compose run --rm crawler pytest -q /app/tests -m "not integration"

소량 실제 검색 테스트:

docker compose run --rm crawler python -m src.cli discover-search ^
--keyword "육류" ^
--batch-id 20260723-jaeseong-test-001 ^
--max-products 5 ^
--max-scrolls 3

소량 실제 카테고리 테스트:

docker compose run --rm crawler python -m src.cli discover-category ^
--category-code 910 ^
--batch-id 20260723-jaeseong-test-002 ^
--max-products 5 ^
--max-scrolls 3

발견 결과 확인:

type datasets\discovery\20260723-jaeseong-test-001\discovered_products.csv
type datasets\discovery\20260723-jaeseong-test-002\discovered_products.csv

24. 구현 순서

다음 순서를 따른다.

현재 crawler 코드 및 사용자 변경사항 확인

URL 파서와 정규 URL 생성 함수 구현

Discovery 데이터 모델 구현

URL 목록 모드 구현

Discovery CSV 및 manifest exporter 구현

Playwright 상품 링크 추출기 구현

검색어 모드 구현

무한 스크롤 및 종료 조건 구현

카테고리 모드 구현

상품 ID 중복 제거 구현

실패 CSV 구현

collect-details와 기존 상세 수집기 연결

단위 테스트 실행

검색 5건 실제 테스트

카테고리 5건 실제 테스트

생성된 CSV 검토 후 수집량 확대

처음부터 100건 이상 수집하지 않는다.

25. 완료 조건

URL 목록

product_urls.txt의 빈 줄·주석 무시

상품 ID 추출

쿼리스트링 제거

중복 URL 제거

Discovery CSV 생성

검색어

한글 검색어 URL 인코딩

검색 페이지 접근

/goods/{id} 링크 발견

최대 상품 수 제한

최대 스크롤 횟수 제한

연속 신규 상품 없음 종료

중복 상품 ID 제거

카테고리

category code URL 생성

category URL 직접 입력 지원

둘 중 하나만 받는 입력 검증

카테고리 상품 링크 발견

상품 수와 스크롤 제한 적용

산출물

discovered_products.csv

manifest.json

오류 발생 시 discovery_failures.csv

UTF-8-SIG CSV

기존 배치 덮어쓰기 방지

collect-details 입력 연결

기존 OCR 파이프라인 회귀 없음

26. MVP 제외 범위

이번 구현에서 제외한다.

컬리 전체 카테고리 자동 순회

카테고리 코드 자동 탐색

모든 검색어 조합 자동 생성

무제한 병렬 크롤링

로그인 및 CAPTCHA 우회

프록시 회전

상품 가격·리뷰·재고 수집

OCR 파서 규칙 전면 개편

KFIA 데이터 매칭

PostgreSQL 적재

관리자 UI

27. AI IDE 작업 보고 형식

구현 전 다음 내용을 먼저 보고한다.

현재 프로젝트에서 확인한 관련 파일

유지해야 할 기존 사용자 변경사항

수정할 파일 목록

새로 추가할 파일 목록

구현 순서

발견한 위험 또는 불확실한 선택자

구현 후 다음 내용을 보고한다.

구현한 기능 요약

CLI 명령 목록

실행한 단위 테스트와 결과

실제 컬리 검색·카테고리 테스트 여부

생성된 CSV·manifest 경로

발견된 상품 수와 중복 제거 수

실패 또는 남은 제약

다음 권장 작업

실제 컬리 DOM을 확인하지 못한 선택자는 완성된 사실처럼 보고하지 않는다. 추정한 부분과 실제 검증한 부분을 구분한다.
