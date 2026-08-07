# 9단계 — Rust 도입 판단 하네스

## 목표

Rust를 학습·유행 목적이 아니라 측정된 병목에만 도입한다. 기본 구현은 Python+Polars다.

## 1차 전략

직접 Rust를 작성하기 전에 다음 Rust 기반 Python 도구를 활용한다.

- Polars
- Parquet/Arrow engine
- 필요 시 DuckDB

## Rust 후보 작업

- 대량 파일 탐색과 checksum
- JSON/JSONL batch compaction
- manifest 생성
- schema-independent artifact validation
- JSONL/CSV → Parquet 변환
- 안정된 Unicode/단위 tokenizer

## Rust 비후보

- OCR 모델 실행
- 식약처/컬리 최종값 선택
- 매칭 임계치 정책
- review/approval 규칙
- Dagster orchestration
- Console UI

## Benchmark 하네스

```text
benchmarks/
├─ fixtures/
│  ├─ small/
│  ├─ medium/
│  └─ large/
├─ python_baseline.py
├─ run_benchmarks.py
└─ reports/
```

측정 항목:

- wall-clock time
- CPU time
- peak RSS
- rows/files per second
- output checksum equality
- build/image size 변화

## 도입 게이트

Rust 구현은 다음 조건을 모두 만족할 때만 채택한다.

1. profiler로 특정 단계가 실제 병목임을 확인했다.
2. Python+Polars 최적화를 먼저 수행했다.
3. 대표 fixture에서 결과가 byte 또는 semantic equivalent다.
4. 목표 단계의 개선이 전체 pipeline 시간/메모리에 의미 있는 영향을 준다.
5. Windows/Linux Docker build와 CI를 유지할 수 있다.
6. 유지보수 비용과 오류 경계가 문서화됐다.

수치 기준은 benchmark 결과를 본 뒤 ADR에서 결정하고 임의로 선행 결정하지 않는다.

## 선택 가능한 통합 방식

### 권장: 독립 CLI

```text
artifact-compiler validate|compile
입력: 경로/manifest
출력: JSON report/Parquet
```

### 제한적: PyO3/Maturin

하나의 계산 함수가 명확한 병목일 때만 Python extension으로 사용한다.

## 완료 조건

- Rust 미도입도 정상적인 결론으로 허용된다.
- 채택 시 Python baseline과 correctness test가 계속 유지된다.
- Rust 실패가 원본 artifact를 손상시키지 않는다.

## AI 지시문

```text
먼저 benchmark와 profiler를 만들고 Python+Polars baseline을 측정해.
측정 결과 없이 Rust 코드를 생성하지 마. Rust 후보가 gate를 통과하면 별도 ADR과 독립 CLI 설계부터 제안해.
```
