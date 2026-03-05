import json
import tomllib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

_HISTORY_FILE = Path.home() / ".cosomil-scripts" / "uvrun" / "history.json"
_HISTORY_MAX = 10


def _get_project_name(project_dir: Path) -> str | None:
    """pyproject.toml から [project].name を読む。失敗時は None。"""
    toml_path = project_dir / "pyproject.toml"
    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("name") or None
    except Exception:
        return None


def _read_history() -> list[dict]:
    try:
        return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_history(history: list[dict]) -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _is_valid_entry(entry: dict, pick_script: Callable[[Path], Path]) -> bool:
    """既存の履歴エントリが現時点でも有効かチェックする。"""
    directory = entry.get("directory")
    if not directory:
        return False
    project_dir = Path(directory)
    try:
        if not project_dir.is_dir():
            return False
        if not (project_dir / "pyproject.toml").is_file():
            return False
        pick_script(project_dir)
    except Exception:
        return False
    return True


def load_valid_history(pick_script: Callable[[Path], Path]) -> list[dict]:
    """バリデーション済みの履歴エントリを返す。"""
    history = _read_history()
    return [h for h in history if _is_valid_entry(h, pick_script)]


def try_record_history(project_dir: Path, pick_script: Callable[[Path], Path]) -> None:
    """
    以下を両方満たす場合のみ履歴に追記・更新する:
      - project_dir に pyproject.toml が存在する
      - pick_script のチェックに成功する
    保存前に既存の全エントリも再バリデーションし、無効なものを除去したうえで
    最新10件に絞って保存する。
    """
    if not (project_dir / "pyproject.toml").is_file():
        return
    try:
        pick_script(project_dir)
    except FileNotFoundError:
        return

    name = _get_project_name(project_dir) or project_dir.name
    now = datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    entry = {
        "name": name,
        "directory": str(project_dir),
        "last_run": now,
    }

    history = _read_history()
    # 既存エントリを再バリデーション（同一ディレクトリ分は除去してから追加するため先に除く）
    history = [
        h
        for h in history
        if h.get("directory") != entry["directory"] and _is_valid_entry(h, pick_script)
    ]
    history.insert(0, entry)
    history = history[:_HISTORY_MAX]
    _write_history(history)
