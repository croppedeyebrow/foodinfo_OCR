# 6단계 — Python·Polars 표준화 계층

## 목표

Python을 개발 언어로 유지하면서 Polars lazy engine으로 Silver 변환을 구현한다.

## 변환 범위

- 컬럼명과 타입 표준화
- HTML/제어문자/공백 정리
- 저장방법 enum 변환
- 소비기한 값·단위·기준 분리
- 상품/식품 식별자 생성
- 출처와 신뢰도 필드 보존
- invalid record 분리

## 금지 범위

- 컬리와 식약처 중 최종값 선택
- Gold 승인
- 저신뢰도 데이터를 임의 보완
- Python row loop/UDF 남용

## Polars 원칙

- `scan_csv`, `scan_ndjson`, `scan_parquet` 사용
- expression 기반 변환 우선
- schema를 명시하고 silent inference를 최소화
- 가능한 마지막에 `collect`
- row별 Python UDF는 사용 이유와 benchmark를 남김
- 결과를 Parquet으로 저장

## 표준 함수 계약

```python
def normalize_kurly_batch(
    input_artifact: ArtifactRef,
    output_dir: Path,
    contract_version: str,
) -> TransformationResult:
    ...
```

`TransformationResult`에는 output artifact, row counts, rejected rows, metrics가 포함된다.

## 테스트 데이터

- 냉장/냉동/실온 표현
- 제조일/포장일/수령일 기준
- 일/개월/년 단위
- 복수 소비기한 문장
- 빈 문자열과 OCR 오인식
- 한글·영문·특수문자 혼합

## 성능 기준선

대표 fixture 크기를 소·중·대로 고정하고 처리시간, peak memory, rows/sec를 기록한다. 성능 숫자를 통과 조건으로 임의 하드코딩하지 말고 baseline 대비 회귀율을 관리한다.

## 완료 조건

- 같은 입력과 버전은 결정적인 Parquet 결과를 만든다.
- invalid row가 유실되지 않고 rejection artifact로 남는다.
- Python row loop 없이 주요 변환이 수행된다.

## AI 지시문

```text
기존 normalizer를 Python+Polars lazy pipeline으로 확장해.
업무상 최종값 선택은 하지 말고 source별 Silver schema까지만 변환해.
모든 invalid row와 변환 metric을 별도 artifact로 남겨.
```
