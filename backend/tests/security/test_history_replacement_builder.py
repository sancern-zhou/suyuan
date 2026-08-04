import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / ".github"
    / "scripts"
    / "build_filter_repo_replacements.py"
)
SPEC = importlib.util.spec_from_file_location("history_replacement_builder", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_load_secrets_deduplicates_and_orders_longest_first(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            [
                {"Secret": "short-secret"},
                {"Secret": "a-much-longer-secret"},
                {"Secret": "short-secret"},
                {"Secret": "REDACTED"},
            ]
        ),
        encoding="utf-8",
    )

    assert MODULE.load_secrets(report) == [
        "a-much-longer-secret",
        "short-secret",
    ]


def test_write_replacements_creates_private_exclusive_file(tmp_path):
    output = tmp_path / "replacements.txt"

    MODULE.write_replacements(output, ["runtime-secret"])

    assert output.stat().st_mode & 0o777 == 0o600
    assert output.read_text(encoding="utf-8") == (
        "literal:runtime-secret==>***REMOVED***\n"
    )
    with pytest.raises(FileExistsError):
        MODULE.write_replacements(output, ["another-secret"])


@pytest.mark.parametrize("secret", ["line1\nline2", "left==>right"])
def test_load_secrets_rejects_unsafe_filter_repo_syntax(tmp_path, secret):
    report = tmp_path / "report.json"
    report.write_text(json.dumps([{"Secret": secret}]), encoding="utf-8")

    with pytest.raises(ValueError):
        MODULE.load_secrets(report)
