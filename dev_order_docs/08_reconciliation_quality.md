# 8단계 — 컬리–KFIA 대조와 품질검토 UI

## 목표

컬리 Silver와 KFIA Reference Silver를 결정적으로 매칭하고, 불확실한 결과를 자동 승인하지 않는 품질 흐름을 구현한다.

## 매칭 순서

1. 명시적 식품 코드 또는 관리된 매핑
2. 표준화된 식품명 exact match
3. category·storage 조건부 후보
4. fuzzy candidate
5. evidence와 confidence 계산
6. 임계치 미만 또는 복수 후보는 수동 검토

매칭 임계값과 우선순위는 승인된 rule 문서 없이 임의 생성하지 않는다.

## 결과 상태

- `APPROVED`
- `REVIEW_REQUIRED`
- `REJECTED`
- `NO_REFERENCE`

## 품질 영역

- Schema: 필수 컬럼·타입·계약 버전
- Completeness: 상품명·storage·소비기한·source
- Validity: 양수·단위·confidence 범위
- Consistency: 저장조건·값 차이·중복·충돌
- Lineage: 모든 결과가 양쪽 Silver artifact를 참조하는지

## UI

- 대조 실행과 진행상태
- 매칭률·미매칭·검토필요·거절 건수
- 상품별 양쪽 값·차이·근거·rule version
- 수동 승인/거절/후보 선택과 사유 입력
- 검토 결정 후 해당 결과만 재처리

## 완료 조건

- 같은 입력과 rule version은 같은 결과를 만든다.
- 불확실한 레코드가 누락되거나 자동 승인되지 않는다.
- 검토자·시각·사유·대상 버전이 기록된다.
- 품질 rule별 통과율과 실패 샘플을 UI에서 확인할 수 있다.
