import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvrun.main
from uvrun.main import (
    _INTERRUPTED_EXIT_CODE,
    _is_marimo_notebook,
    _run_script,
    _script_command,
)


def test_script_command_runs_regular_python_script_with_uv_run(tmp_path):
    script = tmp_path / "main.py"
    script.write_text("print('hello')\n", encoding="utf-8")

    assert _script_command(tmp_path, script) == ["uv", "run", "main.py"]


def test_script_command_runs_marimo_notebook_with_marimo_run(tmp_path):
    script = tmp_path / "main.py"
    script.write_text(
        "import marimo as mo\n\napp = mo.App()\n",
        encoding="utf-8",
    )

    assert _is_marimo_notebook(script) is True
    assert _script_command(tmp_path, script) == [
        "uv",
        "run",
        "marimo",
        "-q",
        "run",
        "main.py",
    ]


def test_marimo_detection_ignores_comments_and_strings(tmp_path):
    script = tmp_path / "main.py"
    script.write_text(
        "# import marimo\ntext = 'import marimo as mo'\n",
        encoding="utf-8",
    )

    assert _is_marimo_notebook(script) is False


def test_run_script_kills_marimo_process_immediately_on_keyboard_interrupt(
    tmp_path, monkeypatch, capsys
):
    script = tmp_path / "main.py"
    script.write_text("import marimo as mo\n", encoding="utf-8")
    process = _InterruptingProcess()
    calls = []

    monkeypatch.setattr(uvrun.main.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        uvrun.main, "_kill_process", lambda p: calls.append(("kill", p))
    )
    monkeypatch.setattr(
        uvrun.main,
        "_terminate_process",
        lambda p, timeout: calls.append(("terminate", p, timeout)),
    )

    assert _run_script(tmp_path, interrupt_timeout=5.0) == _INTERRUPTED_EXIT_CODE
    assert calls == [("kill", process)]
    assert (
        "[情報] marimo notebook を終了するには Ctrl+C を押してください。"
        in capsys.readouterr().out
    )


def test_run_script_terminates_regular_process_on_keyboard_interrupt(
    tmp_path, monkeypatch, capsys
):
    script = tmp_path / "main.py"
    script.write_text("print('hello')\n", encoding="utf-8")
    process = _InterruptingProcess()
    calls = []

    monkeypatch.setattr(uvrun.main.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        uvrun.main, "_kill_process", lambda p: calls.append(("kill", p))
    )
    monkeypatch.setattr(
        uvrun.main,
        "_terminate_process",
        lambda p, timeout: calls.append(("terminate", p, timeout)),
    )

    assert _run_script(tmp_path, interrupt_timeout=5.0) == _INTERRUPTED_EXIT_CODE
    assert calls == [("terminate", process, 5.0)]
    assert "marimo notebook を終了するには" not in capsys.readouterr().out


class _InterruptingProcess:
    def wait(self):
        raise KeyboardInterrupt
