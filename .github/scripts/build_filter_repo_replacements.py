#!/usr/bin/env python3
"""Build a git-filter-repo replacement file from a private Gitleaks JSON report.

The input report must be generated without ``--redact`` and treated as a secret.
This helper never prints secret values and creates its output with mode 0600.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


REPLACEMENT = "***REMOVED***"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def load_secrets(report_path: Path) -> list[str]:
    findings = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(findings, list):
        raise ValueError("Gitleaks report must contain a JSON array")

    secrets = set()
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        secret = finding.get("Secret")
        if not isinstance(secret, str) or not secret or secret == "REDACTED":
            continue
        if "\n" in secret or "\r" in secret or "==>" in secret:
            raise ValueError("Unsupported multiline or delimiter-containing secret")
        secrets.add(secret)

    # Replace longer values first when one leaked value contains another.
    return sorted(secrets, key=lambda value: (-len(value), value))


def write_replacements(output_path: Path, secrets: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(output_path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        for secret in secrets:
            output.write(f"literal:{secret}==>{REPLACEMENT}\n")


def main() -> int:
    args = parse_args()
    secrets = load_secrets(args.report)
    if not secrets:
        raise SystemExit("No non-redacted secrets found in report")
    write_replacements(args.output, secrets)
    print(f"replacement_count={len(secrets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
