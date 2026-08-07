# 현재 Collection 아키텍처

## Docker 서비스

| 서비스 | 역할 |
|---|---|
| `console` | FastAPI/Jinja 단계별 실행 UI |
| `crawler` | Playwright 상품 발견·상세 수집 |
| `ocr-parser` | 이미지 판별·PaddleOCR·DOM 병합 |
| `normalizer` | 현재 DB 연결 확인, 향후 Silver 변환 |
| `postgres` | 향후 pipeline metadata |

## 현재 실행 흐름

```text
1. discover-urls/search/category
2. collect-details
2.5 classify-images
3. process-batch
```

## 현재 저장 위치

- `datasets/discovery/{batch_id}`
- `datasets/crawl_raw`
- `datasets/detail_images`
- `datasets/ocr_raw`
- `outcome/{member}/{batch_id}`

## 보존 원칙

기존 CLI, Console route, batch ID, 팀원 output 구조를 신규 플랫폼 구축 중에도 유지한다. 새 경로는 compatibility adapter와 shadow output으로 먼저 도입한다.

## 알려진 제약

- Console 작업 상태는 메모리 중심
- 로컬 Console이 Docker socket을 사용
- `products.csv`만으로는 전체 lineage가 부족
- normalizer와 PostgreSQL은 아직 실질 기능이 없음
