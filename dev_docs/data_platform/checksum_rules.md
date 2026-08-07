# Contract content_hash 규칙

## 목적

같은 논리적 payload는 항상 같은 `content_hash`(SHA-256 hex, 소문자 64자)를 만든다.

## 계산 범위

1. 입력은 JSON object(dict)다.
2. 모든 깊이의 `content_hash` 키는 해시 입력에서 **제외**한다.
3. object 키는 문자열로 변환한 뒤 **사전식 오름차순** 정렬한다.
4. array는 **기존 순서를 유지**한다 (정렬하지 않음).
5. `datetime`/`date`는 ISO-8601 문자열로 직렬화한다.
6. `Decimal`은 고정소수 문자열(`format(value, "f")`)로 직렬화한다.
7. UTF-8, compact separators `(",", ":")`, `ensure_ascii=False`, `allow_nan=False`.
8. 직렬화된 바이트열에 SHA-256을 적용한다.

구현: `apps/normalizer/src/checksum.py`.

## 검증

`validate-contract`는 schema/pydantic 검사 후, payload에 `content_hash`가 있으면 재계산값과 비교한다. 불일치 시 `CHECKSUM_MISMATCH`.

## 버전

- backward compatible 필드 추가: minor 증가
- 필드 삭제·타입/의미 변경: major 증가
- 지원하지 않는 major는 `UNSUPPORTED_SCHEMA_VERSION`으로 즉시 거부
