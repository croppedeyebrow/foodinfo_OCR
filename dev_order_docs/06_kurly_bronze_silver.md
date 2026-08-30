# 6단계 — 컬리 Bronze·Silver UI

## 목표

accepted 팀원 배치를 UI에서 Bronze로 검증·보존하고 Polars 기반 Silver로 표준화한다.

## Bronze

- accepted manifest와 checksum 검증
- 원본 필드·DOM·OCR evidence 보존
- `source_record_id`와 content hash 생성
- 계약 오류를 quarantine으로 분리
- 성공 후에만 Bronze artifact 승격

## Silver

- 동일 상품 레코드 그룹화
- 상품 ID 기준 중복 통합
- HTML·제어문자·공백 정리
- 저장방법 enum 표준화
- 소비기한 값·단위·기준 분리
- DOM 값과 OCR 후보·confidence 보존
- 대표값 선택 근거와 rule version 기록
- Parquet·검토 CSV·manifest 생성

임의의 OCR 보정값이나 도메인 임계값을 만들지 않는다. 확정되지 않은 값은 `REVIEW_REQUIRED`로 보존한다.

## UI

```text
[Bronze 생성] → 입력/정상/격리 건수
[Silver 정제] → 고유상품/파싱성공/검토필요/evidence 보존율
[상품 근거 보기] → DOM·OCR 후보와 선택 근거
```

## 완료 조건

- 동일 입력·버전의 결과가 결정적이다.
- 입력 56건 같은 반복 상품이 고유 상품 단위로 통합된다.
- OCR evidence가 유실되지 않는다.
- 실패해도 기존 성공 Silver가 훼손되지 않는다.
- Console에서 실행·결과·재실행을 처리할 수 있다.
