# 컬리N마트 상세페이지 크롤링 및 OCR 파서

컬리N마트 상품 상세페이지의 상품정보제공고시 이미지를 수집하고 OCR로 원문을 추출하기 위한 Docker 기반 프로젝트입니다.

## 구성

- `crawler`: Playwright 기반 상세페이지 분석 및 이미지 수집
- `ocr-parser`: PaddleOCR 기반 OCR 및 고시정보 1차 파싱
- `normalizer`: OCR JSONL 검증, 식약처 기준 데이터 통합 및 DB 적재
- `postgres`: 공통 정제 결과 저장

원본 이미지와 OCR 중간 결과는 `datasets`에 저장되며 Git에서 제외됩니다.

## Windows CMD 최초 실행

```cmd
cd /d C:\Dev\work_python\crowling_ocr_parser
setup.cmd
```

## 단계별 확인

```cmd
docker compose build crawler
docker compose run --rm crawler

docker compose build ocr-parser
docker compose run --rm ocr-parser

docker compose up -d postgres
docker compose build normalizer
docker compose run --rm normalizer
```

## 종료

```cmd
docker compose down
```

`docker compose down -v`는 PostgreSQL 데이터까지 삭제하므로 일반 종료에 사용하지 않습니다.

## OCR 결과 생성

상품 입력 manifest는 `datasets/input/products.csv`를 사용합니다.

```csv
batch_id,original_product_id,product_name,product_url,image_path,source_image_url,source_site
20260719-local-001,123456,고향만두 1kg,https://example.com/product/123456,images/123456.jpg,https://example.com/disclosure.jpg,KURLY_N_MART
```

배치 실행:

```cmd
docker compose run --rm ocr-parser python -m src.cli process-batch --manifest /data/input/products.csv
```

생성 결과:

```text
datasets/ocr_raw/{상품ID}_{이미지해시}.json
datasets/ocr_output/{배치ID}/products.csv
datasets/ocr_output/{배치ID}/failures.csv
```

## 다음 기능 개발 목표

1. `datasets/input/product_urls.txt`에서 상품 URL 한 개 읽기
2. 상세페이지에서 상품 ID, 상품명, 고시정보 이미지 URL 추출
3. JPEG를 `datasets/images`에 저장
4. 이미지 SHA-256과 실패 코드를 기록
5. 저장 이미지에 OCR 적용
6. 소비기한·보관방법 원문을 JSONL로 출력
