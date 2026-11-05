from copy import deepcopy

import pytest

from deploy.client.production_release_preflight import (
    EXPECTED_PHASES,
    approved_prior_schema_head,
)


PRIOR_COMMIT = "a" * 40
CANDIDATE_COMMIT = "b" * 40


def _passed_report():
    return {
        "status": "passed",
        "prior_commit": PRIOR_COMMIT,
        "candidate_commit": CANDIDATE_COMMIT,
        "production_release": False,
        "data_is_synthetic": True,
        "completed_phases": list(EXPECTED_PHASES),
        "cleanup": "passed",
        "prior_schema_head": "previous_head",
        "candidate_schema_head": "candidate_head",
    }


def test_preflight_returns_prior_head_only_for_complete_exact_commit_lifecycle():
    assert approved_prior_schema_head(
        _passed_report(),
        prior_commit=PRIOR_COMMIT,
        candidate_commit=CANDIDATE_COMMIT,
    ) == "previous_head"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "failed"),
        ("prior_commit", "c" * 40),
        ("candidate_commit", "d" * 40),
        ("production_release", True),
        ("data_is_synthetic", False),
        ("completed_phases", EXPECTED_PHASES[:-1]),
        ("cleanup", "failed"),
        ("prior_schema_head", "invalid revision"),
    ],
)
def test_preflight_rejects_unproven_schema_authorization(field, value):
    report = deepcopy(_passed_report())
    report[field] = value

    with pytest.raises(ValueError):
        approved_prior_schema_head(
            report,
            prior_commit=PRIOR_COMMIT,
            candidate_commit=CANDIDATE_COMMIT,
        )
