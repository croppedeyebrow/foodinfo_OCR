# 교차 정제와 품질 정책

## 매칭 순서

1. 명시적 식품 코드
2. 표준화된 이름 exact match
3. category와 storage 조건
4. fuzzy candidate
5. confidence와 근거 계산
6. 불확실한 결과 수동 검토

## 결과 상태

- `APPROVED`
- `REVIEW_REQUIRED`
- `REJECTED`

최종 선택에는 컬리 값, 식약처 값, 선택 값, rule ID/version, match type, confidence를 남긴다. 실패 record를 조용히 버리지 않는다.
