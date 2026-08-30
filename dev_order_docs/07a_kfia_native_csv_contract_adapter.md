# Stage 07A — KFIA Native CSV 계약·Adapter 수정 지시서

## 0. 문서 사용 목적

이 문서는 `foodinfo_OCR` 저장소에서 KFIA 기준 데이터 등록 기능을 실제 `ref_data_parser` 출력 형식에 맞게 수정하기 위한 개발 지시서다.

- 대상 저장소: `https://github.com/croppedeyebrow/foodinfo_OCR`
- 외부 데이터 생산자: `https://github.com/croppedeyebrow/ref_data_parser`
- 실제 입력 파일: `shelf_life_output.csv`
- 실행 시점: `07_kfia_reference_pipeline.md` 구현 전 또는 구현 중 계약 수정 단계
- 사용자 작업 방식: CLI가 아니라 Console UI

구현 전 다음 문서를 읽는다.

```text
AGENTS.md
dev_order_docs/README.md
dev_order_docs/00_execution_rules.md
dev_order_docs/02_contracts_and_storage.md
dev_order_docs/03_pipeline_metadata.md
dev_order_docs/05_pipeline_ui_foundation.md
dev_order_docs/07_kfia_reference_pipeline.md
```

---

## 1. 문제 정의

등록 대상 파일 종류는 맞다. `ref_data_parser`가 생성한 `shelf_life_output.csv`를 KFIA Reference 입력으로 사용한다.

그러나 현재 Console 검증 로직은 다음 필드를 필수로 요구한다.

```text
품목코드
식품명 또는 food_name
source_pdf
페이지 또는 page_number
원문 또는 raw_text
```

실제 파일에는 다음 차이가 있다.

| 현재 기대 필드 | 실제 CSV | 판단 |
|---|---|---|
| `품목코드` | `품목코드` | 일치 |
| `식품명` / `food_name` | 없음, `식품유형`만 존재 | 의미가 다르므로 대체 금지 |
| `source_pdf` | `source_pdf` | 일치 |
| `페이지` / `page_number` | `source_page` | 이름만 다름 |
| `원문` / `raw_text` | 없음 | 필수에서 제외 |

`식품유형`은 개별 식품명이 아니라 KFIA 분류다. `식품유형`을 `food_name`으로 이름만 바꾸면 데이터 의미가 왜곡된다.

따라서 CSV를 수작업으로 수정하지 말고, Console 입력 계약과 Native Adapter를 실제 export에 맞게 수정한다.

---

## 2. 실제 입력 구조

실제 CSV는 963행, 16개 컬럼으로 구성된다.

```text
품목코드
식품유형
성상
포장방법
기존유통기한
보존유통온도
보관방법
기준온도
품질안전한계기간_일
안전계수
소비기한참고값_일
단위
온도별_상세_json
source_pdf
source_page
추출일시
```

원본 파일은 UTF-8 BOM 또는 UTF-8 인코딩을 안전하게 처리해야 한다.

---

## 3. 목표 데이터 흐름

```text
shelf_life_output.csv
→ Console 파일 등록
→ KFIA Native Input Contract 검증
→ Native CSV Adapter
→ KFIA Bronze 963건 보존
→ KFIA 품질검사
→ 정상/검토/격리 분류
→ KFIA Reference Silver
```

Bronze와 Silver 계약을 분리한다. 업로드 형식과 표준화 결과 형식을 하나의 계약으로 검증하지 않는다.

---

## 4. KFIA Native Input Contract

신규 계약 파일을 추가한다.

```text
contracts/kfia_native_export.schema.json
```

### 4.1 필수 컬럼

```text
품목코드
식품유형
소비기한참고값_일
단위
온도별_상세_json
source_pdf
source_page
추출일시
```

### 4.2 조건부 또는 선택 컬럼

```text
성상
포장방법
기존유통기한
보존유통온도
보관방법
기준온도
품질안전한계기간_일
안전계수
```

파일 전체에서 컬럼 자체는 존재해야 하지만 일부 행의 빈 값은 Bronze 등록을 차단하지 않는다. 행 단위 품질검사에서 처리한다.

### 4.3 제거할 잘못된 필수 조건

다음 필드는 Native Input 필수값으로 요구하지 않는다.

```text
food_name
식품명
raw_text
원문
page_number
페이지
```

`source_page`를 공식 Native Input 필드로 인정한다.

---

## 5. Native CSV Adapter

권장 구현 위치:

```text
apps/normalizer/src/adapters/kfia_native_csv.py
```

Adapter는 컬럼명 변환뿐 아니라 원본값 보존과 타입 변환 경계를 담당한다.

### 5.1 매핑

| 원본 CSV | Bronze/Silver 필드 | 처리 |
|---|---|---|
| `품목코드` | `reference_item_code` | 문자열 그대로 |
| `식품유형` | `food_type` | 문자열 그대로 |
| 없음 | `food_name` | 생성 금지, nullable |
| `성상` | `appearance_raw` | 원문 보존 |
| `포장방법` | `packaging_raw` | 원문 보존 |
| `기존유통기한` | `existing_shelf_life_raw` | 원문 보존 |
| `보존유통온도` | `storage_temperature_raw` | 원문 보존 |
| `보관방법` | `storage_type_raw` | 원문 보존 |
| `보관방법` | `storage_type` | Silver에서 enum 변환 |
| `기준온도` | `reference_temperature_raw` | 원문 보존 |
| `품질안전한계기간_일` | `quality_limit_days` | nullable number |
| `안전계수` | `safety_factor_raw` | 원문 보존 |
| `안전계수` | `safety_factor` | 검증된 경우에만 number |
| `소비기한참고값_일` | `reference_shelf_life_days` | number |
| `단위` | `original_unit` | `일` 또는 `시간` 보존 |
| `온도별_상세_json` | `temperature_details` | JSON 파싱 |
| `source_pdf` | `source_document` | 문자열 그대로 |
| `source_page` | `source_page` | integer |
| `추출일시` | `extracted_at` | datetime |

### 5.2 레코드 식별자

```text
source_record_id = kfia:{reference_item_code}
```

필요한 경우 content checksum을 결합해 artifact 내부 레코드 ID를 만든다.

```text
record_id = kfia:{reference_item_code}:{content_hash 일부}
```

### 5.3 구현 예시

```python
def adapt_kfia_native_row(row: dict[str, str]) -> KfiaBronzeRecord:
    return KfiaBronzeRecord(
        reference_item_code=row["품목코드"].strip(),
        food_type=_nullable(row["식품유형"]),
        food_name=None,
        appearance_raw=_nullable(row["성상"]),
        packaging_raw=_nullable(row["포장방법"]),
        existing_shelf_life_raw=_nullable(row["기존유통기한"]),
        storage_temperature_raw=_nullable(row["보존유통온도"]),
        storage_type_raw=_nullable(row["보관방법"]),
        reference_temperature_raw=_nullable(row["기준온도"]),
        quality_limit_days=_nullable_decimal(row["품질안전한계기간_일"]),
        safety_factor_raw=_nullable(row["안전계수"]),
        reference_shelf_life_days=_required_decimal(
            row["소비기한참고값_일"]
        ),
        original_unit=row["단위"].strip(),
        temperature_details=json.loads(row["온도별_상세_json"]),
        source_document=row["source_pdf"].strip(),
        source_page=int(row["source_page"]),
        extracted_at=_parse_datetime(row["추출일시"]),
        raw_payload=row,
    )
```

Adapter는 오류를 숨기지 않는다. 실패 행은 행 번호·품목코드·필드·오류 코드를 포함해 rejection artifact로 보낸다.

---

## 6. KFIA Bronze 원칙

CSV 963건을 원본 의미 그대로 보존한다.

```text
입력 963건
→ Bronze 963건 또는 정상 Bronze + 명시적 rejection
→ 행 제거 금지
```

Bronze에 보존할 정보:

- 원본 16개 필드
- 등록 파일명과 checksum
- dataset version
- parser version 또는 ref_data_parser commit
- 등록자
- 등록시각
- Native contract version
- source row number

Bronze에서는 `실온/상온`을 덮어쓰거나 의심 안전계수를 자동 수정하지 않는다.

---

## 7. Reference Silver Contract

신규 또는 기존 계약을 실제 기준 데이터 의미에 맞게 수정한다.

```text
contracts/kfia_reference_silver.schema.json
```

핵심 예시:

```json
{
  "reference_item_code": "17-1-1-1",
  "food_type": "소시지",
  "food_name": null,
  "storage_type_raw": "실온",
  "storage_type": "AMBIENT",
  "reference_temperature_raw": "35℃",
  "reference_shelf_life_days": 180,
  "original_unit": "일",
  "source_document": "17. 식육가공품 및 포장육-1.pdf",
  "source_page": 458,
  "review_status": "APPROVED"
}
```

`food_type`과 `food_name`은 의미를 분리한다. 현재 데이터에는 `food_name`이 없으므로 nullable로 유지한다.

---

## 8. 품질 규칙

다음 규칙을 코드와 결과 metadata에 stable rule ID로 구현한다.

| Rule ID | 검사 | 실패 처리 |
|---|---|---|
| `KFIA-001` | 품목코드 존재·유일성 | REJECTED |
| `KFIA-002` | 소비기한 참고값이 양수 | REJECTED |
| `KFIA-003` | 안전계수 0 초과 1 이하 | REVIEW_REQUIRED |
| `KFIA-004` | 품목코드 첫 번호와 source PDF 분류 일치 | REVIEW_REQUIRED |
| `KFIA-005` | 온도별 상세 JSON 유효 | REJECTED |
| `KFIA-006` | 보관방법 표준화 가능 | REVIEW_REQUIRED |
| `KFIA-007` | 식품유형·보관방법 등 핵심값 존재 | REVIEW_REQUIRED |
| `KFIA-008` | source PDF·page 존재 | REJECTED |

실제 샘플에서 확인된 현황:

```text
전체 레코드                 963
고유 품목코드               963
소비기한 참고값 숫자 성공    963
온도별 상세 JSON 성공        963
안전계수 1 초과               70
핵심 필드 일부 누락           24
품목코드·PDF 분류 불일치       1
```

안전계수 70건은 PDF 분류번호가 잘못 추출된 것으로 의심된다. 예:

```text
11. 특수의료용도식품.pdf → 안전계수 11.0
16. 농산가공식품류.pdf   → 안전계수 16.0
23. 즉석식품류.pdf       → 안전계수 23.0
```

Silver에서 `소비기한 ÷ 품질안전한계기간`으로 임의 보정하지 않는다. 파서를 수정하거나 원문 검토 결정을 받아야 한다.

품목코드 `2-1-4-5`, 원본 `20. 수산가공식품류-1.pdf`도 자동으로 `20-1-4-5`로 수정하지 않는다.

---

## 9. 저장방법 표준화

Silver에서만 다음 mapping을 적용한다.

| 원본 | 표준값 |
|---|---|
| `냉장` | `REFRIGERATED` |
| `냉동` | `FROZEN` |
| `실온` | `AMBIENT` |
| `상온` | `AMBIENT` |
| 빈 값·알 수 없음 | `UNKNOWN` |

반드시 `storage_type_raw`도 함께 보존한다.

---

## 10. Console UI 수정

### 10.1 등록 화면

```text
KFIA 기준 데이터 파일  [shelf_life_output.csv]
Dataset version         [KFIA-YYYY-MM 또는 사용자 입력]
Parser version          [commit/tag]
등록자                   [operator]

[계약 검증] [KFIA Bronze 등록]
```

### 10.2 검증 결과

```text
전체 행                  963
품목코드                 있음
식품유형                 있음
소비기한 참고값          있음
source_pdf               있음
source_page              있음
온도별 상세 JSON         유효
raw_text                 미제공 · 선택 필드

판정: Native 계약 통과 / Bronze 등록 가능
      Silver 승격 전 품질검사 필요
```

다음 오류 메시지는 제거한다.

```text
필수 컬럼 food_name이 없습니다.
필수 컬럼 raw_text가 없습니다.
필수 컬럼 page_number가 없습니다.
```

### 10.3 Stage 상태

```text
파일 등록
→ Native 계약 검증
→ KFIA Bronze
→ 품질검사
→ KFIA Reference Silver
```

각 단계는 `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `REVIEW_REQUIRED` 상태를 표시한다.

---

## 11. 주요 수정 대상

실제 저장소를 먼저 조사하고 이름은 현재 구조에 맞게 조정한다.

```text
apps/console/src/main.py 또는 KFIA route
apps/console/src/templates/step_platform.html 또는 KFIA template
apps/console/src/summaries.py

apps/normalizer/src/contracts.py
apps/normalizer/src/adapters/kfia_native_csv.py
apps/normalizer/src/stages/kfia_bronze.py
apps/normalizer/src/stages/kfia_silver.py
apps/normalizer/src/quality/kfia_rules.py

contracts/kfia_native_export.schema.json
contracts/kfia_reference_silver.schema.json

tests/fixtures/kfia/
tests/test_kfia_native_adapter.py
tests/test_kfia_contracts.py
tests/test_kfia_pipeline_ui.py
tests/test_kfia_quality.py
```

UI route에 CSV parsing·단위 변환·품질 규칙을 직접 작성하지 않는다.

---

## 12. 테스트 요구사항

### 계약

- 실제 16개 컬럼 header 통과
- `food_name` 없이 통과
- `raw_text` 없이 통과
- `source_page`를 올바른 필드로 인식
- 필수 컬럼 누락 시 이해 가능한 오류
- 잘못된 `온도별_상세_json` 거부

### Adapter

- `식품유형 → food_type`
- `food_name=None`
- `source_page → integer`
- 숫자·datetime·JSON 변환
- UTF-8 BOM 처리
- 원본 row 보존
- 변환 실패 행 rejection 보존

### 품질

- 안전계수 11.0은 REVIEW_REQUIRED
- `실온/상온 → AMBIENT`
- 식품유형 누락은 REVIEW_REQUIRED
- 소비기한 누락·음수는 REJECTED
- 품목코드·PDF 분류 불일치 감지
- 자동 보정이나 행 유실 없음

### UI

- OPERATOR만 파일 등록 가능
- 실제 fixture CSV 계약 검증 성공
- Bronze 등록 결과 건수 표시
- 품질검사 결과 표시
- 선행 단계 실패 시 Silver 버튼 비활성 및 서버 거부
- 중복 클릭과 동일 checksum 재등록 방지

### 회귀

- 컬리 수집·OCR·제출 흐름 유지
- 컬리 Bronze·Silver 계약 영향 없음
- 기존 metadata migration·repository 테스트 통과

---

## 13. 완료 조건

- [ ] 실제 `shelf_life_output.csv`가 Console에서 등록된다.
- [ ] `food_name`, `raw_text`, `page_number` 부재로 실패하지 않는다.
- [ ] `식품유형`이 `food_type`으로 저장되고 `food_name`으로 오용되지 않는다.
- [ ] `source_page`가 원본 페이지 필드로 처리된다.
- [ ] 963건과 원본 16개 필드가 Bronze에서 보존된다.
- [ ] 품질 문제 레코드가 조용히 제거되지 않는다.
- [ ] 안전계수 이상값이 자동 수정되지 않는다.
- [ ] KFIA 품질 요약이 UI에 표시된다.
- [ ] 정상 레코드와 검토 대상이 구분된다.
- [ ] 같은 파일·dataset version 재등록이 멱등하다.
- [ ] 모든 신규·회귀 테스트가 통과한다.

---

## 14. 구현 결과 보고 형식

```text
1. 변경 파일 목록
2. Native Input Contract 변경 내용
3. 실제 CSV 컬럼 매핑 결과
4. food_type과 food_name 분리 방식
5. raw_text 부재 처리 방식
6. Bronze 입력·정상·검토·격리 건수
7. 안전계수 이상값 처리 방식
8. Console UI 변경 내용
9. 실행한 테스트와 결과
10. 남은 parser 원천 수정 작업
```

완료하지 못한 항목을 성공한 것처럼 보고하지 않는다.
