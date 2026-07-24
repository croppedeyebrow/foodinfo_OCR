from __future__ import annotations

from conftest import use_app

use_app("ocr-parser")

from src.batch_filter import batch_belongs_to_member  # noqa: E402


def test_batch_belongs_to_member() -> None:
    assert batch_belongs_to_member("20260723-jaeseong-001", "jaeseong")
    assert batch_belongs_to_member("20260723-sunyeong-001", "sunyeong")
    assert not batch_belongs_to_member("20260723-jaeseong-001", "woohee")
    assert not batch_belongs_to_member("20260723-jaeseong-001", "sunyeong")
