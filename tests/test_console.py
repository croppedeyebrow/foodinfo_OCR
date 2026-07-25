from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import _clear_src_modules

CONSOLE_ROOT = Path(__file__).resolve().parents[1] / "apps" / "console"
_clear_src_modules()
cleaned = [
    path
    for path in sys.path
    if "apps/crawler" not in path.replace("\\", "/")
    and "apps/ocr-parser" not in path.replace("\\", "/")
    and "apps/console" not in path.replace("\\", "/")
]
sys.path[:] = [str(CONSOLE_ROOT), *cleaned]

from src.runner import (  # noqa: E402
    JobRunner,
    JobState,
    build_classify_images_command,
    build_collect_details_command,
    build_compose_command,
    build_discover_category_command,
    build_discover_search_command,
    build_discover_urls_command,
    build_process_batch_command,
)
from src.summaries import (  # noqa: E402
    count_csv_rows,
    list_discovery_batches,
    summarize_text_checks,
)


def test_build_compose_command_base() -> None:
    cmd = build_compose_command("crawler", ["health"])
    assert cmd[:5] == ["docker", "compose", "run", "--rm", "crawler"]
    assert cmd[-2:] == ["src.cli", "health"]


def test_build_discover_search_command() -> None:
    cmd = build_discover_search_command("20260726-jaeseong-001", "육류", 5, 3)
    assert "discover-search" in cmd
    assert "--keyword" in cmd and "육류" in cmd
    assert "--batch-id" in cmd and "20260726-jaeseong-001" in cmd
    assert "--max-products" in cmd and "5" in cmd
    assert "--max-scrolls" in cmd and "3" in cmd


def test_build_discover_urls_command() -> None:
    cmd = build_discover_urls_command("20260726-jaeseong-001")
    assert "discover-urls" in cmd
    assert "/data/input/product_urls.txt" in cmd


def test_build_discover_category_code() -> None:
    cmd = build_discover_category_command(
        "b1",
        category_code="910",
        max_products=5,
        max_scrolls=3,
    )
    assert "--category-code" in cmd and "910" in cmd
    assert "--category-url" not in cmd


def test_build_discover_category_requires_code_or_url() -> None:
    with pytest.raises(ValueError):
        build_discover_category_command("b1", max_products=5, max_scrolls=3)


def test_build_collect_and_classify_force() -> None:
    collect = build_collect_details_command("b1", force=True)
    assert "collect-details" in collect
    assert "--force" in collect
    assert "/data/discovery/b1/discovered_products.csv" in collect

    classify = build_classify_images_command("b1", force=True)
    assert classify[4] == "ocr-parser"
    assert "classify-images" in classify
    assert "--force" in classify


def test_build_process_batch_command() -> None:
    cmd = build_process_batch_command("b1")
    assert "process-batch" in cmd
    assert "/data/discovery/b1/crawled_products.csv" in cmd
    assert "--batch-id" in cmd and "b1" in cmd


def test_job_runner_rejects_second_job() -> None:
    runner = JobRunner(project_root=".")
    with runner._lock:
        runner._status.state = JobState.RUNNING
    with pytest.raises(RuntimeError, match="already running"):
        runner.start("ocr", ["echo", "no"])


def test_count_csv_rows(tmp_path: Path) -> None:
    missing = count_csv_rows(tmp_path / "missing.csv")
    assert missing.exists is False
    assert missing.row_count == 0

    path = tmp_path / "rows.csv"
    path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8-sig")
    summary = count_csv_rows(path)
    assert summary.exists is True
    assert summary.row_count == 2


def test_summarize_text_checks(tmp_path: Path) -> None:
    path = tmp_path / "image_text_check.csv"
    path.write_text(
        "schema_version,batch_id,original_product_id,image_path,"
        "text_presence,detect_method,confidence,checked_at,notes\n"
        "1.0,b,1,a.jpg,HAS_TEXT,HEURISTIC,0.9,t,\n"
        "1.0,b,1,b.jpg,NO_TEXT,HEURISTIC,0.9,t,\n"
        "1.0,b,1,c.jpg,UNKNOWN,HEURISTIC,0.1,t,\n"
        "1.0,b,1,d.jpg,NO_TEXT,HEURISTIC,0.8,t,\n",
        encoding="utf-8-sig",
    )
    summary = summarize_text_checks(path)
    assert summary.row_count == 4
    assert summary.has_text == 1
    assert summary.no_text == 2
    assert summary.unknown == 1


def test_list_discovery_batches(tmp_path: Path) -> None:
    (tmp_path / "20260726-jaeseong-001").mkdir()
    (tmp_path / "20260726-sunyeong-001").mkdir()
    (tmp_path / "readme.txt").write_text("x", encoding="utf-8")
    all_batches = list_discovery_batches(tmp_path)
    assert all_batches == ["20260726-sunyeong-001", "20260726-jaeseong-001"]
    filtered = list_discovery_batches(tmp_path, member_filter="jaeseong")
    assert filtered == ["20260726-jaeseong-001"]
