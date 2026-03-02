import shutil
import subprocess
import sys
from pathlib import Path

from uvrun.history import try_record_history


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


def main():
    if len(sys.argv) < 2:
        print("使い方: uvproj-run <project_dir>")
        print(
            "ヒント: プロジェクトフォルダーをショートカットにドラッグ＆ドロップしてください。"
        )
        sys.exit(2)

    try:
        project_dir = _ensure_dir(sys.argv[1])
        script_path = _pick_script(project_dir)
    except Exception as e:
        print(f"[起動失敗] {e}")
        sys.exit(1)

    # uv が見つからない場合は分かりやすく
    if shutil.which("uv") is None:
        print(
            "[起動失敗] 'uv' コマンドが見つかりません。uv をインストールし PATH を通してください。"
        )
        sys.exit(127)

    # uv run は project コンテキストと cwd がズレると混乱しやすいので、
    # uv 側にも --directory を渡しつつ、subprocess 側の cwd も project_dir に寄せます。
    # また、uv run の引数衝突を避けるため `--` を挟みます。 (uv run の一般的なパターン)
    script_rel = script_path.relative_to(project_dir)

    cmd = [
        "uv",
        "run",
        str(script_rel),
    ]
    completed = subprocess.run(cmd, cwd=str(project_dir))
    try_record_history(project_dir, _pick_script)
    sys.exit(completed.returncode)


if __name__ == "__main__":
    main()
