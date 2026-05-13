"""
Check uv user configuration policy.

Exit codes:
  0: OK
  2: Error (unexpected)
"""

import os
import re
import sys
from datetime import timedelta
from pathlib import Path

from tomlkit import dumps, parse
from tomlkit.toml_document import TOMLDocument


MIN_EXCLUDE_NEWER = timedelta(days=2)
TEMPLATE_CONFIG_TEXT = """# リリースされてから2日以上経過したパッケージのみインストールを許可する
# （サプライチェーン攻撃で侵害されたパッケージは、多くの場合1日以内に発見、削除される）
exclude-newer = \"2 days\"
"""


def load_toml(path: Path) -> TOMLDocument:
    with path.open("r", encoding="utf-8") as f:
        return parse(f.read())


def write_toml(path: Path, document: TOMLDocument) -> None:
    path.write_text(dumps(document), encoding="utf-8")


def user_config_path() -> Path:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "uv" / "uv.toml"
        return Path.home() / "AppData" / "Roaming" / "uv" / "uv.toml"

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "uv" / "uv.toml"
    return Path.home() / ".config" / "uv" / "uv.toml"


def load_template_toml() -> TOMLDocument:
    return parse(TEMPLATE_CONFIG_TEXT)


def clone_document(document: TOMLDocument) -> TOMLDocument:
    return parse(dumps(document))


def render_config(config: TOMLDocument | None) -> str:
    if config is None:
        return "<none>"
    return dumps(config).rstrip("\n")


# --- exclude-newer parsing ---
_DURATION_WORD_RE = re.compile(
    r"^\s*(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\s*$",
    re.IGNORECASE,
)
_ISO8601_RE = re.compile(
    r"^\s*P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?\s*$",
    re.IGNORECASE,
)
_RFC3339_RE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s*$")

_UNIT_SECONDS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "week": 604800,
    "weeks": 604800,
}


def parse_exclude_newer_value(value: object) -> tuple[bool, timedelta | None, str]:
    if not isinstance(value, str):
        return (False, None, "exclude-newer is not a string")

    s = value.strip()
    if _RFC3339_RE.match(s):
        return (
            False,
            None,
            "exclude-newer is a fixed timestamp (not a rolling duration)",
        )

    match = _DURATION_WORD_RE.match(s)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        seconds_per_unit = _UNIT_SECONDS.get(unit)
        if seconds_per_unit is None:
            return (False, None, f"unknown unit in exclude-newer: {unit}")
        return (True, timedelta(seconds=amount * seconds_per_unit), "")

    match = _ISO8601_RE.match(s)
    if match:
        days = int(match.group(1) or 0)
        hours = int(match.group(2) or 0)
        minutes = int(match.group(3) or 0)
        seconds = int(match.group(4) or 0)
        return (
            True,
            timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds),
            "",
        )

    return (False, None, "exclude-newer is not a recognized duration format")


def enforce_policy(config: TOMLDocument | None) -> tuple[TOMLDocument, list[str]]:
    template = load_template_toml()
    template_value = template.get("exclude-newer")
    if template_value is None:
        raise ValueError("template config に exclude-newer がありません")

    if config is None:
        return clone_document(template), ["exclude-newer"]

    updated_config = clone_document(config)
    updated_fields: list[str] = []

    value = updated_config.get("exclude-newer")
    is_duration, duration, _ = parse_exclude_newer_value(value)
    if not is_duration or duration is None or duration < MIN_EXCLUDE_NEWER:
        updated_config["exclude-newer"] = template_value
        updated_fields.append("exclude-newer")

    return updated_config, updated_fields


def main() -> int:
    try:
        config_path = user_config_path().expanduser()
        existing_config = load_toml(config_path) if config_path.is_file() else None

        print(f"対象ファイル: {config_path}")
        print()
        print("更新前の設定ファイル:")
        print("```")
        print(render_config(existing_config))
        print("```")
        print()

        updated_config, updated_fields = enforce_policy(existing_config)

        print("更新後の設定ファイル:")
        print("```")
        print(render_config(updated_config))
        print("```")

        if updated_fields:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            write_toml(config_path, updated_config)

        updated_fields_label = ", ".join(updated_fields) if updated_fields else "なし"
        print(f"更新した設定項目: {updated_fields_label}")
        return 0
    except Exception as e:
        print(f"ERROR: unexpected failure: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
