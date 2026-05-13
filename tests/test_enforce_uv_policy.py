from pathlib import Path
import sys

from tomlkit import dumps, parse


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from enforce_uv_policy.main import enforce_policy


def test_enforce_policy_creates_template_config_when_missing():
    updated_config, updated_fields = enforce_policy(None)

    assert updated_fields == ["exclude-newer"]
    assert updated_config["exclude-newer"] == "2 days"


def test_enforce_policy_keeps_compliant_config_unchanged():
    config = parse('# keep me\nexclude-newer = "2 days"\nfoo = "bar"\n')

    updated_config, updated_fields = enforce_policy(config)

    assert updated_fields == []
    assert dumps(updated_config) == dumps(config)


def test_enforce_policy_adds_missing_exclude_newer():
    config = parse('# keep me\nfoo = "bar"\n')

    updated_config, updated_fields = enforce_policy(config)

    assert updated_fields == ["exclude-newer"]
    assert updated_config["exclude-newer"] == "2 days"
    assert updated_config["foo"] == "bar"
    assert "# keep me" in dumps(updated_config)


def test_enforce_policy_replaces_invalid_exclude_newer_and_preserves_comments():
    config = parse('# keep me\nexclude-newer = "1 day"\nfoo = "bar"\n')

    updated_config, updated_fields = enforce_policy(config)

    assert updated_fields == ["exclude-newer"]
    assert updated_config["exclude-newer"] == "2 days"
    assert updated_config["foo"] == "bar"
    assert "# keep me" in dumps(updated_config)
