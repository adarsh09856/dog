#!/usr/bin/env python3
"""Extract rollback authorization only from a complete lifecycle report."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_PHASES = [
    "prior_release_validated",
    "synthetic_data_seeded",
    "backup_created",
    "candidate_upgraded_and_data_verified",
    "rollback_release_and_data_verified",
]
_REVISION = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def approved_prior_schema_head(
    report: dict[str, Any], *, prior_commit: str, candidate_commit: str,
) -> str:
    """Return a prior schema head only when exact commits completed acceptance."""
    if not _COMMIT.fullmatch(prior_commit) or not _COMMIT.fullmatch(candidate_commit):
        raise ValueError("Release lifecycle commits must be full Git SHA-1 values")
    if (
        report.get("status") != "passed"
        or report.get("prior_commit") != prior_commit
        or report.get("candidate_commit") != candidate_commit
        or report.get("production_release") is not False
        or report.get("data_is_synthetic") is not True
        or report.get("completed_phases") != EXPECTED_PHASES
        or report.get("cleanup") != "passed"
    ):
        raise ValueError("Lifecycle report did not prove the required prior-schema upgrade and rollback")
    schema_head = report.get("prior_schema_head")
    candidate_head = report.get("candidate_schema_head")
    if (
        not isinstance(schema_head, str)
        or not _REVISION.fullmatch(schema_head)
        or not isinstance(candidate_head, str)
        or not _REVISION.fullmatch(candidate_head)
    ):
        raise ValueError("Lifecycle report has invalid schema revision metadata")
    return schema_head


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--prior-commit", required=True)
    parser.add_argument("--candidate-commit", required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise SystemExit("Lifecycle report must be a JSON object")
    try:
        schema_head = approved_prior_schema_head(
            report,
            prior_commit=args.prior_commit,
            candidate_commit=args.candidate_commit,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"prior_schema_head={schema_head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
