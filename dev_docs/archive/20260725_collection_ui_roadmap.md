> 상태: COMPLETED / ARCHIVED
>
> 2026-07-25 당시 Collection UI와 이미지 판별 기능을 위한 과거 로드맵이다.
> 현재 구현 지시로 사용하지 않는다.

# 개발 로드맵 — 2026-07-25

오늘 필요한 개발·수정 사항 정리.

---

## 현황 요약

현재 파이프라인은 3단계로 동작한다.

1. **상품 발견** (`discover-urls` / `discover-search` / `discover-category`)
2. **상세 수집** (`collect-details`)
3. **OCR·최종 CSV** (`process-batch`)

실행은 Docker CLI 명령에 의존하며, 배치 ID·경로·옵션을 매번 수동으로 맞춰야 한다.  
또한 상세 이미지 중 텍스트가 없는 순수 사진까지 OCR 대상이 되어 `OCR_TEXT_EMPTY` 실패·불필요 처리가 발생한다.

---

## 1. 단계별 확인·수정·실행 UI

### 목적

CMD에서 명령어를 매번 수정하지 않고, **눈으로 확인하면서** 단계별로 진행할 수 있는 UI를 만든다.

### 요구사항

| 항목 | 내용 |
|---|---|
| 단계 진행 | 1→2→3 순서를 UI에서 선택·실행 |
| 확인 | 각 단계 입력값(배치 ID, 키워드, 카테고리, manifest 경로 등)을 화면에서 확인 |
| 수정 | 실행 전 파라미터를 UI에서 바로 수정 |
| 체크 | 단계 완료 여부, 산출물 경로, 성공/실패 건수를 화면에 표시 |
| 실행 | UI 버튼으로 Docker/파이프라인 명령 실행 (또는 동등한 백엔드 호출) |

### 단계별 UI에서 다룰 내용 (초안)

**1단계 — 발견**

- 모드 선택: URL 목록 / 검색어 / 카테고리
- 입력: `product_urls.txt` 미리보기·편집, 검색어, 카테고리 코드/URL
- 옵션: `batch-id`, `max-products`, `max-scrolls`
- 결과 확인: `discovered_products.csv` 미리보기, 발견 건수, 실패 로그

**2단계 — 상세 수집**

- 입력: discovery 배치 선택 (`discovered_products.csv`)
- 옵션: `--force` 여부
- 결과 확인: `crawled_products.csv`, `crawl_raw` / `detail_images` 요약

**3단계 — OCR**

- 입력: 해당 배치 `crawled_products.csv`
- 옵션: `BATCH_MEMBER`, `--batch-id`
- 결과 확인: `outcome/{팀원}/{배치ID}/products.csv`, `failures.csv`

### 구현 방향 (검토)

- 로컬 웹 UI (예: Streamlit / FastAPI+간단 프론트) 또는 데스크톱 폼
- 기존 CLI·Docker 명령을 UI가 호출하는 방식 우선 (파이프라인 로직 재작성 최소화)
- Windows / Mac 팀원 모두 사용 가능한 형태

### 완료 조건

- [ ] 3단계를 UI에서 순서대로 실행 가능
- [ ] 실행 전 파라미터 확인·수정 가능
- [ ] 각 단계 결과(경로·건수·실패)를 화면에서 확인 가능
- [ ] `runscript.md`의 핵심 명령을 UI로 대체 가능

---

## 2. 이미지 텍스트 유무 판별 (OCR 전 필터)

### 목적

크롤링으로 모은 상세 이미지 중

- **글자 없는 순수 사진** → OCR 스킵
- **텍스트 추출 대상 이미지** → OCR 진행

을 미리 구별·체크한다.

### 배경

현재는 이미지가 있으면 OCR을 시도하고, 텍스트가 없으면 `OCR_TEXT_EMPTY`로 실패 기록되는 경우가 많다.  
불필요한 OCR 비용·실패 노이즈를 줄이기 위해 **사전 판별**이 필요하다.

### 요구사항

| 항목 | 내용 |
|---|---|
| 판별 시점 | 상세 이미지 다운로드 이후 ~ OCR 직전 (2단계 후처리 또는 3단계 전처리) |
| 판별 결과 | 예: `HAS_TEXT` / `NO_TEXT` (또는 `OCR_CANDIDATE` / `SKIP_PHOTO`) |
| 기록 | 이미지 메타 또는 manifest 컬럼 / 별도 체크 CSV에 저장 |
| UI 연동 (1번과 연계) | 이미지 목록에서 판별 결과를 눈으로 확인·수동 재분류 가능하면 좋음 |
| OCR 연동 | `NO_TEXT`는 자동 스킵, `HAS_TEXT`만 `process-batch` 대상 |

### 판별 방식 후보 (구현 시 선택)

1. **경량 휴리스틱**: 엣지/대비·OCR 엔진 저비용 프리패스·이미지 높이·영역 위치
2. **기존 PaddleOCR 빠른 패스**: 텍스트 블록 수·신뢰도 임계값으로 판정
3. **수동 체크**: UI에서 사람이 최종 확인 (자동화 + 검수)

MVP는 **자동 판별 + 결과 기록**, 가능하면 UI에서 재확인.

### 완료 조건

- [ ] 이미지별 텍스트 유무 판별 결과 저장
- [ ] `NO_TEXT` 이미지는 OCR 단계 자동 제외
- [ ] `HAS_TEXT`만 OCR·최종 CSV에 반영
- [ ] (선택) UI에서 판별 결과 목록 확인·수정

---

## 3. 멤버별 수집 데이터 조회 페이지 (분할)

### 목적

각 멤버(`jaeseong` / `sunyeong` / `woohee`)가 크롤링·OCR로 모은 데이터를 **멤버별로 나뉜 페이지**에서 조회할 수 있게 한다.  
다른 멤버 작업과 섞이지 않고, 본인 산출물만 눈으로 확인한다.

### 요구사항

| 항목 | 내용 |
|---|---|
| 멤버 분할 | 멤버마다 독립 페이지(또는 탭/라우트) 제공 |
| 조회 범위 | 해당 멤버의 discovery 배치, 상세 수집 결과, OCR `products.csv` / `failures.csv` |
| 배치 목록 | `outcome/{멤버}/`·관련 discovery 배치를 목록으로 선택 |
| 상세 보기 | 상품 행·이미지·실패 사유를 화면에서 확인 |
| 권한/구분 | 기본은 본인 멤버 페이지; (선택) 전체 멤버 목록은 읽기 전용 네비게이션 |

### 페이지 구성 초안

```text
/members/jaeseong   → jaeseong 수집·OCR 데이터
/members/sunyeong   → sunyeong 수집·OCR 데이터
/members/woohee     → woohee 수집·OCR 데이터
```

각 멤버 페이지에서:

- 배치 ID 목록
- `discovered_products` / `crawled_products` / `products.csv` 테이블 미리보기
- (연계) 이미지 텍스트 유무 판별 결과
- 실패(`failures.csv`, `discovery_failures.csv`) 요약

### 데이터 소스

- `outcome/{멤버}/{배치ID}/products.csv`
- `outcome/{멤버}/{배치ID}/failures.csv`
- `datasets/discovery/{배치ID}/` (배치 ID에 멤버명이 포함된 것만 필터)
- (선택) `detail_images` 썸네일

### 완료 조건

- [ ] 멤버별 전용 조회 페이지(또는 동등한 분할 UI) 존재
- [ ] 해당 멤버 배치·CSV만 노출
- [ ] 배치 선택 후 수집/OCR 결과를 화면에서 확인 가능
- [ ] 1번 실행 UI·2번 이미지 판별 화면과 네비게이션으로 연결 가능

---

## 우선순위·작업 순서 (제안)

| 순서 | 작업 | 이유 |
|---|---|---|
| 1 | 이미지 텍스트 유무 판별 (백엔드) | OCR 실패·낭비 감소, CLI만으로도 바로 이득 |
| 2 | 판별 결과를 manifest/CSV에 연결 | 3단계 입력 정리 |
| 3 | 단계별 실행 UI (MVP) | 명령어 수작업 제거 |
| 4 | 멤버별 수집 데이터 조회 페이지 | 팀원별 결과 확인·공유 |
| 5 | UI에 이미지 판별 검수 화면 연결 | 1·2·3·4 시너지 |

---

## 범위 밖 (오늘 로드맵에서 제외)

- 네이버 컬리N마트 상세 DOM 전용 파서 고도화 (별도 과제)
- KFIA 매칭·DB 적재·normalizer
- 로그인/CAPTCHA 우회
- 무제한 대량 수집

---

## 메모

- 배치·팀원 분리는 이미 `BATCH_MEMBER` + `discovery/{배치ID}/` + `outcome/{멤버}/` 기준으로 정리됨.
- 멤버별 조회 페이지는 이 디렉터리 구조를 그대로 읽으면 된다.
- UI는 기존 CLI를 감싸는 형태가 안전하다.
- Mac OCR(Paddle segfault) 이슈는 별도 환경 제약으로 유지; UI에서도 3단계 실행 환경(Windows/Linux 권장)을 안내하는 것이 좋다.
