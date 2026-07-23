from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from conftest import use_app


def test_write_raw_json(tmp_path: Path) -> None:
    use_app("crawler")
    from src.models import CrawledProductRecord
    from src.raw_exporter import write_raw_json

    record = CrawledProductRecord(
        batch_id="20260719-jaeseong-001",
        original_product_id="5047857",
        product_url="https://www.kurly.com/goods/5047857",
        requested_url="https://www.kurly.com/goods/5047857",
        product_name_raw="테스트 상품",
        collected_at=datetime.now(ZoneInfo("Asia/Seoul")),
    )
    path = write_raw_json(record, tmp_path)
    assert path.name == "5047857.json"
    assert path.is_file()
    assert "5047857" in path.read_text(encoding="utf-8")


def test_write_utf8_sig_csv(tmp_path: Path) -> None:
    use_app("ocr-parser")
    from src.exporter import append_product_csv
    from src.models import MergedProductRecord

    output = tmp_path / "products.csv"
    record = MergedProductRecord(
        batch_id="20260719-jaeseong-001",
        source_site="KURLY",
        original_product_id="5047857",
        product_name_raw="테스트",
        product_url="https://www.kurly.com/goods/5047857",
        parser_version="0.2.0",
        validation_status="MATCHED",
        parse_status="COMPLETED",
    )
    append_product_csv(record, output)
    raw = output.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with output.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["original_product_id"] == "5047857"


def test_skip_duplicate_source_record(tmp_path: Path) -> None:
    use_app("ocr-parser")
    from src.exporter import append_product_csv, build_dedupe_key, load_existing_source_keys
    from src.models import MergedProductRecord

    output = tmp_path / "products.csv"
    record = MergedProductRecord(
        batch_id="20260719-jaeseong-001",
        source_site="KURLY",
        original_product_id="5047857",
        product_name_raw="테스트",
        product_url="https://www.kurly.com/goods/5047857",
        parser_version="0.2.0",
        validation_status="MATCHED",
        parse_status="COMPLETED",
        source_record_id="KURLY:5047857:a93f8812b142",
        image_sha256="a93f8812b142" + ("0" * 52),
    )
    append_product_csv(record, output)
    keys = load_existing_source_keys(output)
    assert "KURLY:5047857:a93f8812b142" in keys
    assert build_dedupe_key("KURLY", "5047857", record.image_sha256) in keys
