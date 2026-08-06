from __future__ import annotations

import re

# Per-item completion lines emitted by crawler / ocr-parser CLIs.
_STEP_PATTERNS: dict[str, re.Pattern[str]] = {
    "collect": re.compile(
        r"^(OK:|SKIP:|FAILED:)",
        re.MULTILINE,
    ),
    "classify": re.compile(
        r"^(HAS_TEXT|NO_TEXT|UNKNOWN):",
        re.MULTILINE,
    ),
    "ocr": re.compile(
        r"^(OK:|SKIP_NO_TEXT:|FAILED:)",
        re.MULTILINE,
    ),
    # Discovery usually finishes in one burst; treat max_products as soft total.
    "discover": re.compile(
        r"(Discovered=\d+|discover-search|discover-category|discover-urls)",
        re.MULTILINE,
    ),
}


def count_progress_events(step: str, log: str) -> int:
    pattern = _STEP_PATTERNS.get(step)
    if pattern is None or not log:
        return 0
    if step == "discover":
        # Prefer explicit Discovered=N when present.
        match = re.search(r"Discovered=(\d+)", log)
        if match:
            return int(match.group(1))
        return 0
    return len(pattern.findall(log))


def progress_percent(done: int, total: int | None) -> int | None:
    if total is None or total <= 0:
        return None
    return max(0, min(100, int(round(100 * done / total))))
