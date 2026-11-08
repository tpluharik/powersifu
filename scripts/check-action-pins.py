#!/usr/bin/python3
"""Reject unpinned external GitHub Actions workflow dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ACTION_REFERENCE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def unpinned_actions(workflow: Path) -> list[str]:
    failures: list[str] = []
    for reference in ACTION_REFERENCE.findall(workflow.read_text(encoding="utf-8")):
        if reference.startswith("./") or reference.startswith("docker://"):
            continue
        _action, separator, revision = reference.rpartition("@")
        if not separator or not FULL_COMMIT.fullmatch(revision):
            failures.append(reference)
    return failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    for pattern in ("*.yml", "*.yaml"):
        for workflow in sorted((root / ".github" / "workflows").glob(pattern)):
            failures.extend(
                f"{workflow.relative_to(root)}: {reference}"
                for reference in unpinned_actions(workflow)
            )
    if failures:
        print("External actions must use full commit SHAs:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
