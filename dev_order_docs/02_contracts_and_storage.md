# 2단계 — 데이터 계약과 저장 계층

## 목적

CSV 파일 연결이 아니라 versioned contract와 immutable artifact로 각 단계를 연결한다. 기존 구현은 보존하고 KFIA·Gold 계약을 후속 단계에서 확장한다.

## 계층

```text
Candidate → Accepted → Bronze → Silver → Reconciled → Quality → Gold
                          ↘ 실패·불확실 → Quarantine
```

## 형식

| 목적 | 형식 |
|---|---|
| Raw·개별 원문 | JSON/원본 파일 |
| 다수 원문 | JSONL |
| Bronze·Silver·Gold | Parquet |
| 사람 검토 view | CSV |
| 산출물 설명 | Manifest JSON |

## 필수 계약

- collection submission
- Kurly Bronze product
- Kurly Silver freshness
- KFIA reference input
- KFIA Reference Silver
- reconciled freshness
- review decision
- Gold freshness profile

모든 계약은 가능한 범위에서 `schema_version`, dataset/batch ID, source, checksum, parser/code/rule version을 포함한다.

## 저장 경로

```text
datasets/inbox/accepted/{batch_id}
datasets/bronze/kurly/{batch_id}
datasets/silver/kurly/{batch_id}
datasets/reference/inbox/{dataset_version}
datasets/bronze/kfia/{dataset_version}
datasets/silver/kfia/{dataset_version}
datasets/reconciled/{run_id}
datasets/quarantine/{run_id}
datasets/gold/{dataset_version}
```

## 완료 조건

- 같은 입력과 버전이 결정적 checksum을 만든다.
- invalid record가 유실되지 않는다.
- CSV는 공식 source of truth가 아니라 업로드·검토·호환 view로 한정된다.
- 기존 accepted 계약과 호환된다.
