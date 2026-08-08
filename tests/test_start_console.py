from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen

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


def test_run_docker_platform_starts_both_uis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []
    runs: list[list[str]] = []
    opened: list[launcher._ServiceEndpoint] = []
    connecting_closed: list[bool] = []
    monkeypatch.setattr(
        launcher,
        "ensure_docker_ready",
        lambda *, assume_yes: True,
    )
    monkeypatch.setattr(
        launcher,
        "_open_connecting_pages",
        lambda endpoints: (
            opened.extend(endpoints)
            or SimpleNamespace(
                close=lambda: connecting_closed.append(True)
            )
        ),
    )

    def fake_call(command, *, cwd, env=None):
        calls.append((command, env or {}))
        return 0

    def fake_run(command, **_kwargs):
        runs.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    monkeypatch.setattr(launcher.subprocess, "call", fake_call)

    result = launcher._run_docker(
        8787,
        no_browser=False,
        assume_yes=True,
        platform_mode=True,
        dagster_port=3100,
    )

    assert result == 0
    assert runs == [[
        "docker",
        "compose",
        "--profile",
        "platform",
        "up",
        "-d",
        "--build",
        "dagster",
    ]]
    assert calls[0][0] == [
        "docker",
        "compose",
        "up",
        "--build",
        "console",
    ]
    assert calls[0][1]["CONSOLE_PORT"] == "8787"
    assert calls[0][1]["DAGSTER_PORT"] == "3100"
    assert calls[1][0] == [
        "docker",
        "compose",
        "--profile",
        "platform",
        "stop",
        "dagster",
    ]
    assert [endpoint.target_url for endpoint in opened] == [
        "http://127.0.0.1:8787/",
        "http://127.0.0.1:3100/",
    ]
    assert connecting_closed == [True]


def test_run_docker_default_keeps_console_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        launcher,
        "ensure_docker_ready",
        lambda *, assume_yes: True,
    )
    monkeypatch.setattr(
        launcher.subprocess,
        "call",
        lambda command, **_kwargs: commands.append(command) or 0,
    )

    launcher._run_docker(8787, no_browser=True, assume_yes=False)

    assert commands == [
        ["docker", "compose", "up", "--build", "console"]
    ]


def test_connecting_page_is_served_on_temporary_local_port() -> None:
    endpoint = launcher._ServiceEndpoint(
        key="console",
        label="Pipeline Console",
        target_url="http://127.0.0.1:8787/",
        probe_url="http://127.0.0.1:8787/health",
    )
    server = launcher._ConnectingPageServer([endpoint])
    try:
        with urlopen(server.url("console"), timeout=2) as response:
            body = response.read().decode("utf-8")
        assert "Pipeline Console 연결 중" in body
        assert "연결되면 자동으로 이동합니다." in body
        assert "http://127.0.0.1:8787/health" in body
    finally:
        server.close()


def test_dotenv_platform_flag_is_local_and_environment_can_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# local setting\nexport CONSOLE_PLATFORM_MODE='true'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CONSOLE_PLATFORM_MODE", raising=False)
    assert launcher._dotenv_flag(
        "CONSOLE_PLATFORM_MODE",
        dotenv_path=dotenv,
    )

    monkeypatch.setenv("CONSOLE_PLATFORM_MODE", "false")
    assert not launcher._dotenv_flag(
        "CONSOLE_PLATFORM_MODE",
        dotenv_path=dotenv,
    )


def test_main_uses_local_platform_mode_and_console_only_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[bool] = []
    monkeypatch.setattr(
        launcher,
        "_dotenv_flag",
        lambda _name: True,
    )
    monkeypatch.setattr(
        launcher,
        "_run_docker",
        lambda _port, **kwargs: modes.append(kwargs["platform_mode"]) or 0,
    )

    assert launcher.main(["--no-browser"]) == 0
    assert launcher.main(["--no-browser", "--console-only"]) == 0
    assert modes == [True, False]
