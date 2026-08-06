from __future__ import annotations

from src.progress import count_progress_events, progress_percent


def test_count_collect_progress() -> None:
    log = "SKIP: 1\nOK: 2\nFAILED: 3\nCompleted: success=1\n"
    assert count_progress_events("collect", log) == 3


def test_count_classify_progress() -> None:
    log = "HAS_TEXT: a.jpg (HEURISTIC)\nNO_TEXT: b.jpg (HEURISTIC)\nUNKNOWN: c.jpg\n"
    assert count_progress_events("classify", log) == 3


def test_count_ocr_progress() -> None:
    log = "SKIP_NO_TEXT: a.jpg\nOK: 1 -> /outcome/x\nFAILED: 2: boom\n"
    assert count_progress_events("ocr", log) == 3


def test_discover_progress_from_discovered_count() -> None:
    log = "Discovered=5, duplicates=0, status=COMPLETED\n"
    assert count_progress_events("discover", log) == 5


def test_progress_percent() -> None:
    assert progress_percent(0, 10) == 0
    assert progress_percent(5, 10) == 50
    assert progress_percent(10, 10) == 100
    assert progress_percent(3, None) is None
