"""Bounded validation metadata for resource editors; never include user values."""

from collections.abc import Sequence
from typing import Any

FIELDS = frozenset(
    {
        "name",
        "website_url",
        "careers_url",
        "criteria",
        "preferred_skills",
        "required_skills",
        "preferred_keywords",
        "excluded_keywords",
        "job_titles",
        "seniority_preferences",
        "locations",
        "employment_types",
        "remote_policy",
        "experience_min_months",
        "experience_max_months",
        "weights",
        "skills",
        "title",
        "location",
        "experience",
        "employment",
        "keywords",
    }
)
CODES = frozenset(
    {
        "blank_value",
        "source_url",
        "company_identity",
        "duplicate_values",
        "too_many_values",
        "preference_conflict",
        "experience_range",
        "weight_total",
        "weight_without_criteria",
        "missing",
        "extra_forbidden",
        "string_too_long",
        "string_too_short",
        "too_long",
        "int_type",
        "greater_than_equal",
        "less_than_equal",
        "literal_error",
        "string_type",
        "list_type",
    }
)


def safe_issues(errors: Sequence[Any]) -> list[dict[str, str]]:
    issues = []
    for error in errors[:24]:
        fields = [part for part in error["loc"] if isinstance(part, str) and part in FIELDS]
        code = error["type"] if error["type"] in CODES else "invalid_value"
        issues.append({"field": ".".join(fields), "code": code})
    return issues
