import shutil
import subprocess
import sys
import os
import signal
from pathlib import Path

import questionary

from uvrun.history import load_valid_history, try_record_history


def _pick_script(project_dir: Path) -> Path:
    """
    優先順位:
      1) project_dir/__main__.py
      2) project_dir/main.py
      3) (project root直下に .py が1つだけある場合) それ
    """
    p1 = project_dir / "__main__.py"
    if p1.is_file():
        return p1

    p2 = project_dir / "main.py"
    if p2.is_file():
        return p2

    py_files = sorted(
        [p for p in project_dir.glob("*.py") if p.is_file()],
        key=lambda p: p.name.lower(),
    )
    if len(py_files) == 1:
        return py_files[0]

    names = ", ".join(p.name for p in py_files) if py_files else "(none)"
    raise FileNotFoundError(
        "実行対象のスクリプトを特定できません。\n"
        "優先順位: __main__.py -> main.py -> (root直下に .py が1つだけならそれ)\n"
        f"root直下の .py: {names}"
    )


def _ensure_dir(arg: str) -> Path:
    project_dir = Path(arg).expanduser()

    # ショートカットの %1 が置換されずに渡ってきた等の事故を分かりやすくする
    if arg.strip() in {"%1", "%~1"}:
        raise ValueError(
            "プロジェクトフォルダーが渡っていません。フォルダーをショートカットにドラッグ＆ドロップしてください。"
        )

    if not project_dir.exists():
        raise FileNotFoundError(f"指定パスが存在しません: {project_dir}")
    if not project_dir.is_dir():
        raise NotADirectoryError(f"フォルダーではありません: {project_dir}")

    return project_dir.resolve()


_INTERRUPTED_EXIT_CODE = -1


def _terminate_process(process: subprocess.Popen, interrupt_timeout: float) -> None:
    """Ctrl+C 時に子プロセスを段階的に停止する。"""
    if sys.platform == "win32":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            try:
                process.terminate()
            except Exception:
                return
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGINT)
        except Exception:
            try:
                process.terminate()
            except Exception:
                return

    try:
        process.wait(timeout=interrupt_timeout)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        if sys.platform == "win32":
            process.terminate()
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass

    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        try:
            if sys.platform == "win32":
                process.kill()
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired as e:
            raise TimeoutError(
                f"プロセス終了要求後も停止しませんでした。pid={process.pid}, timeout={interrupt_timeout}"
            ) from e


def _run_script(project_dir: Path, interrupt_timeout: float) -> int:
    """スクリプトを実行し終了コードを返す。"""
    script_path = _pick_script(project_dir)
    script_rel = script_path.relative_to(project_dir)
    cmd = ["uv", "run", str(script_rel)]

    process = (
        subprocess.Popen(
            cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, cwd=str(project_dir)
        )
        if sys.platform == "win32"
        else subprocess.Popen(cmd, start_new_session=True, cwd=str(project_dir))
    )

    try:
        return process.wait()
    except KeyboardInterrupt:
        # 子プロセス(S)の実行中断を優先し、uvrun 本体は終了させない
        _terminate_process(process, interrupt_timeout)
        return _INTERRUPTED_EXIT_CODE


_QUIT = object()  # 「終了」選択用センチネル
_ENTER_PATH = object()  # 「パスを入力」選択用センチネル


def _strip_surrounding_quotes(s: str) -> str:
    """先頭・末尾のシングルクォートまたはダブルクォートを取り除く。"""
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    return s


def _validate_project_path(raw: str) -> bool | str:
    """questionary のバリデーター。有効なプロジェクトディレクトリなら True を返す。"""
    text = _strip_surrounding_quotes(raw)
    if not text:
        return "パスを入力してください。"
    p = Path(text).expanduser()
    if not p.exists():
        return f"存在しないパスです: {p}"
    if not p.is_dir():
        return f"ディレクトリではありません: {p}"
    try:
        _pick_script(p.resolve())
    except FileNotFoundError as e:
        return str(e)
    return True


def _select_from_history(first_try: bool) -> Path | None:
    """questionary で履歴からプロジェクトを選択。キャンセル時は None。"""
    history = load_valid_history(_pick_script)

    choices = [
        questionary.Choice(
            title=f"{h['name']}  ({h['directory']})",
            value=Path(h["directory"]),
        )
        for h in history
    ]
    choices.append(
        questionary.Choice(title="[プロジェクトの場所を入力]", value=_ENTER_PATH)
    )
    choices.append(questionary.Choice(title="[終了]", value=_QUIT))

    result = questionary.select(
        "実行するプロジェクトを選択してください:"
        if first_try
        else "次に実行するプロジェクトを選択してください:",
        choices=choices,
    ).ask()

    if result is _QUIT or result is None:
        return None

    if result is _ENTER_PATH:
        raw = questionary.path(
            "プロジェクトフォルダーのパスを入力するかドラッグ＆ドロップしてください:",
            only_directories=True,
            validate=_validate_project_path,
        ).ask()
        if raw is None:
            return None
        return Path(_strip_surrounding_quotes(raw)).expanduser().resolve()

    return result


def main():
    if len(sys.argv) < 2:
        # 引数なし → 履歴から選択
        project_dir = _select_from_history(first_try=True)
        if project_dir is None:
            sys.exit(0)
    else:
        try:
            project_dir = _ensure_dir(sys.argv[1])
            _pick_script(project_dir)  # 事前バリデーション
        except Exception as e:
            print(f"[起動失敗] {e}")
            sys.exit(1)

    # uv が見つからない場合は分かりやすく
    if shutil.which("uv") is None:
        print(
            "[起動失敗] 'uv' コマンドが見つかりません。uv をインストールし PATH を通してください。"
        )
        sys.exit(127)

    while project_dir is not None:
        try:
            returncode = _run_script(project_dir, interrupt_timeout=5.0)
        except TimeoutError:
            print("[中断] スクリプトの中断がタイムアウトしました。")
            returncode = 1
        except Exception as e:
            print(f"[起動失敗] {e}")
            returncode = 1

        if returncode == 0:
            print("\n[成功] スクリプトが正常に終了しました。")
        elif returncode == _INTERRUPTED_EXIT_CODE:
            print("\n[中断] スクリプトを中断しました。")
        else:
            print(f"\n[失敗] スクリプトが終了コード {returncode} で終了しました。")

        print()

        try_record_history(project_dir, _pick_script)

        project_dir = _select_from_history(first_try=False)

    sys.exit(0)


if __name__ == "__main__":
    main()
