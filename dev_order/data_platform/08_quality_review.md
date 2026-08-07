# 8단계 — 데이터 품질과 검토 흐름

## 목표

정제 결과를 자동 승인·수동 검토·거절로 분리하고 품질 결과를 재현 가능하게 저장한다.

## 상태

- `APPROVED`
- `REVIEW_REQUIRED`
- `REJECTED`

## 규칙 분류

### Schema

- 필수 컬럼
- 타입
- enum
- contract version

### Completeness

- 식품명
- storage type
- expiration value/unit/basis
- source record

### Validity

- 소비기한 양수
- 허용 단위
- confidence 범위 0~1
- URL/ID 형식

### Consistency

- 저장방법과 참조 규칙 일치
- 컬리/식약처 차이
- 동일 상품 중복·충돌

## 검토 산출물

```text
datasets/quarantine/{run_id}/
├─ review_required.parquet
├─ review_required.csv
├─ rejected.parquet
└─ quality_report.json
```

CSV는 사람이 수정하는 source가 아니라 검토용 view다. 승인 결과는 별도 review decision contract로 입력한다.

## 품질 규칙 코드

각 규칙은 `rule_id`, version, severity, 설명, 판정함수를 갖는다. rule ID를 재사용해 의미를 바꾸지 않는다.

## 완료 조건

- 실패 record가 조용히 drop되지 않는다.
- rule별 통과율과 실패 샘플을 확인할 수 있다.
- 수동 결정의 사용자·시각·사유·대상 version이 남는다.

## AI 지시문

```text
Schema, completeness, validity, consistency 품질 규칙과 quarantine 산출물을 구현해.
검토 CSV를 직접 Gold source로 사용하지 말고 versioned review decision을 통해 재처리해.
```
