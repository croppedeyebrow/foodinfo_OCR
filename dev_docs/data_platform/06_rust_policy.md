# Rust 도입 정책

## 기본 원칙

Python과 Polars로 먼저 구현하고 benchmark와 profiler가 입증한 병목에만 Rust를 도입한다.

## 후보

- 대량 파일 checksum
- Manifest 생성
- JSON/JSONL compaction
- Artifact validation
- JSONL·CSV → Parquet
- 안정된 tokenizer

## 제외

- OCR
- 교차 보정 정책
- confidence·approval 규칙
- Dagster와 Console

Rust 미도입도 정상적인 기술 결정이다. 도입 시 독립 CLI를 우선하고 PyO3는 단일 계산 함수 병목에만 검토한다.
