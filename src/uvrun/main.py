import shutil
import subprocess
import sys
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


def _run_script(project_dir: Path) -> int:
    """スクリプトを実行し終了コードを返す。"""
    script_path = _pick_script(project_dir)
    script_rel = script_path.relative_to(project_dir)
    cmd = ["uv", "run", str(script_rel)]
    completed = subprocess.run(cmd, cwd=str(project_dir))
    return completed.returncode


_QUIT = object()  # 「終了」選択用センチネル


def _select_from_history() -> Path | None:
    """questionary で履歴からプロジェクトを選択。キャンセル時は None。"""
    history = load_valid_history(_pick_script)
    if not history:
        return None

    choices = [
        questionary.Choice(
            title=f"{h['name']}  ({h['directory']})",
            value=Path(h["directory"]),
        )
        for h in history
    ]
    choices.append(questionary.Choice(title="[終了]", value=_QUIT))

    result = questionary.select(
        "次に実行するプロジェクトを選択してください:",
        choices=choices,
    ).ask()

    if result is _QUIT or result is None:
        return None
    return result


def main():
    if len(sys.argv) < 2:
        # 引数なし → 履歴から選択
        history = load_valid_history(_pick_script)
        if not history:
            print("使い方: uvrun <project_dir>")
            print(
                "ヒント: プロジェクトフォルダーをショートカットにドラッグ＆ドロップしてください。"
            )
            sys.exit(2)
        project_dir = _select_from_history()
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
            returncode = _run_script(project_dir)
        except Exception as e:
            print(f"[起動失敗] {e}")
            returncode = 1

        if returncode == 0:
            print("\n[成功] スクリプトが正常に終了しました。")
        else:
            print(f"\n[失敗] スクリプトが終了コード {returncode} で終了しました。")

        try_record_history(project_dir, _pick_script)

        project_dir = _select_from_history()

    sys.exit(0)


if __name__ == "__main__":
    main()
