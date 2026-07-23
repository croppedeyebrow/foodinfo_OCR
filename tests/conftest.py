from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _clear_src_modules() -> None:
    for name in list(sys.modules):
        if name == "src" or name.startswith("src."):
            del sys.modules[name]


def _resolve_app_root(app_name: str) -> Path:
    tests_dir = Path(__file__).resolve().parent
    project_root = tests_dir.parent
    local_app = project_root / "apps" / app_name
    if local_app.exists():
        return local_app

    # Docker: 현재 서비스의 /app/src 만 마운트된다.
    docker_app = Path("/app")
    marker_files = {
        "crawler": docker_app / "src" / "url_parser.py",
        "ocr-parser": docker_app / "src" / "merge_policy.py",
    }
    marker = marker_files.get(app_name)
    if marker is not None and marker.exists():
        return docker_app

    pytest.skip(f"{app_name} sources are not available in this environment", allow_module_level=True)


def use_app(app_name: str) -> Path:
    """테스트에서 crawler/ocr-parser 중 하나의 src 패키지를 활성화한다."""
    app_root = _resolve_app_root(app_name)
    _clear_src_modules()
    cleaned = [
        path
        for path in sys.path
        if "apps/crawler" not in path.replace("\\", "/")
        and "apps/ocr-parser" not in path.replace("\\", "/")
    ]
    sys.path[:] = [str(app_root), *cleaned]
    return app_root
