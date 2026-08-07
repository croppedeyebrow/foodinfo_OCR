# 7단계 — 식약처 파서 연결 및 교차 정제

## 목표

기존 `ref_data_parser`의 PDF 결과를 공통 계약으로 수용하고 컬리 Silver와 교차 보정한다.

## 통합 방식

- 초기에는 `ref_data_parser`의 versioned export를 입력으로 받는다.
- 코드를 즉시 복사하지 않고 adapter와 계약으로 연결한다.
- 유지보수 중복이 확인되면 별도 migration ADR 후 `apps/mfds-parser`로 이전한다.

## 매칭 단계

1. 명시적 식품 코드
2. 표준화된 식품명 exact match
3. category/storage 조건부 match
4. fuzzy candidate 생성
5. confidence와 근거 계산
6. 임계치 미만은 수동 검토

## 보정 결과에 남길 근거

- 컬리 원본 값
- 식약처 참조 값
- 선택 값
- 선택 rule ID/version
- match type
- confidence
- review status

## 업무 규칙 위치

```text
apps/reconciler/
├─ matcher.py
├─ rules.py
├─ scorer.py
├─ resolver.py
└─ models.py
```

규칙은 Dagster asset이나 Console route에 작성하지 않는다.

## 결정성

같은 입력 artifact, contract version, rule version이면 같은 결과를 생성해야 한다. 현재시간·파일순서·DB 자동 ID에 따라 결과가 달라지지 않게 한다.

## 테스트

- 양쪽 값 일치
- 단위만 다름
- 저장방법 불일치
- 값 차이가 허용범위 초과
- 매칭 후보 복수
- 식약처 reference 없음
- OCR confidence 낮음

## 완료 조건

- 최종값과 선택 근거를 함께 추적할 수 있다.
- 불확실한 데이터를 자동 승인하지 않는다.
- rule version 변경 시 Gold를 재생성할 수 있다.

## AI 지시문

```text
ref_data_parser 결과를 versioned input adapter로 연결하고 reconciler를 구현해.
근거 없는 우선순위나 임계치를 invent하지 말고 모든 선택은 rule ID/version과 evidence를 남겨.
불확실한 경우 REVIEW_REQUIRED로 보존해.
```
