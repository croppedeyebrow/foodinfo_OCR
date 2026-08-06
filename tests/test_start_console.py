from __future__ import annotations

from pathlib import Path

import pytest

import start_console as launcher


def test_docker_cli_exists_false_on_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(launcher.subprocess, "run", boom)
    assert launcher._docker_cli_exists() is False


def test_ensure_docker_ready_when_already_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "_docker_cli_exists", lambda: True)
    monkeypatch.setattr(launcher, "_docker_engine_ready", lambda: True)
    assert launcher.ensure_docker_ready() is True


def test_ensure_docker_ready_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "_docker_cli_exists", lambda: True)
    monkeypatch.setattr(launcher, "_docker_engine_ready", lambda: False)
    monkeypatch.setattr(launcher, "_prompt_yes_no", lambda _msg: False)
    assert launcher.ensure_docker_ready() is False


def test_ensure_docker_ready_starts_and_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "_docker_cli_exists", lambda: True)
    states = {"ready": False}

    def engine_ready() -> bool:
        return states["ready"]

    def start_desktop() -> bool:
        states["ready"] = True
        return True

    monkeypatch.setattr(launcher, "_docker_engine_ready", engine_ready)
    monkeypatch.setattr(launcher, "_start_docker_desktop", start_desktop)
    monkeypatch.setattr(launcher, "_wait_for_docker_engine", lambda timeout=120: True)
    assert launcher.ensure_docker_ready(assume_yes=True) is True


def test_find_docker_desktop_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe = tmp_path / "Docker" / "Docker" / "Docker Desktop.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "x86"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    found = launcher._find_docker_desktop_windows()
    assert found == exe
