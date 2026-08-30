# 7단계 — KFIA 기준 데이터 등록·Bronze·Silver UI

## 목표

독립 저장소 `croppedeyebrow/ref_data_parser`가 생성한 KFIA 소비기한 export를 버전이 있는 기준 데이터로 등록하고 정제한다.

## 통합 경계

- 파서 코드와 대용량 PDF를 `foodinfo_OCR`에 복사하지 않는다.
- `shelf_life_output.csv` 또는 향후 Parquet export를 입력으로 받는다.
- 업로드 파일, dataset version, checksum, parser commit/version, 등록자를 manifest에 기록한다.
- 명칭은 MFDS가 아니라 `KFIA Reference`를 사용한다.

## UI

```text
기준 데이터 파일 [선택]
dataset version   [KFIA-YYYY-MM 또는 명시값]
parser version    [commit/tag]
[계약 검증] [Reference Bronze] [Reference Silver]
```

## Reference Bronze

- 963건 등 입력 row count 확인
- 필수 컬럼·타입·품목코드·원본 단위 검증
- source PDF·page 보존
- 오류 행 quarantine

## Reference Silver

- 한글 컬럼을 공통 영문 계약으로 매핑
- 일·시간 원본 단위와 표준 일 값을 함께 보존
- storage type·temperature 정규화
- 품목코드·식품유형·소비기한 기준을 Parquet으로 저장
- schema·checksum·parser version lineage 기록

## 완료 조건

- UI만으로 등록부터 Reference Silver까지 실행된다.
- 같은 dataset version과 checksum은 중복 등록되지 않는다.
- 원본 PDF 경로·페이지·원래 단위가 추적된다.
- `ref_data_parser` 변경 없이 versioned export 경계로 연결된다.

## 완료 보충 (2026-08-30)

실제 `ref_data_parser` native CSV 형식 반영은 [`07a_kfia_native_csv_contract_adapter.md`](07a_kfia_native_csv_contract_adapter.md)에서 수행했다. 구현·운영 검증 내역은 [`dev_history/07_kfia_reference_pipeline.md`](../dev_history/07_kfia_reference_pipeline.md)를 참고한다.

- `parser_version` UI 입력 제거 → `PIPELINE_CODE_VERSION` 자동 기록
- Bronze/Silver 계약: `kfia_reference_bronze` / `kfia_reference_silver` (Kurly `normalized_freshness`와 분리)
- 운영 검증 `KFIA-2026-08`: Bronze 963/963, Silver 승인 874·검토 89·거절 0
