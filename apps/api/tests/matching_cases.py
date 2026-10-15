"""Seeded, test-only case generator for the matching golden file (values stay out of app code)."""

import json
import random
from pathlib import Path

from app.modules.matching.explain import to_document
from app.modules.matching.scoring import JobFacts, score
from app.modules.preferences.schemas import Criteria

GOLDEN = Path(__file__).parent / "fixtures" / "matching" / "golden.json"
SKILLS = [
    "Python",
    "Go",
    "C++",
    "C#",
    "Node.js",
    ".NET",
    "PostgreSQL",
    "Kubernetes",
    "SQL",
    "React",
]
TITLES = ["Backend Engineer", "Data Analyst", "Product Designer", "Site Reliability Engineer"]
SENIORITY = ["Senior", "Junior", "Lead"]
PLACES = ["Berlin", "Lisbon", "Remote", "Toronto"]
TYPES = ["Full-time", "Part-time", "Contract", "Internship"]
KEYWORDS = ["APIs", "observability", "startup", "on-call"]
MODES = ["remote", "hybrid", "onsite", "unknown"]
JOB_TYPES = ["full_time", "part_time", "contract", "unknown"]
FACTORS = ["skills", "title", "location", "experience", "employment", "keywords"]


def _weights(rng: random.Random, factors: list[str]) -> dict[str, int]:
    cuts = sorted(rng.sample(range(1, 100), len(factors) - 1)) if len(factors) > 1 else []
    parts = [b - a for a, b in zip([0, *cuts], [*cuts, 100], strict=True)]
    return dict.fromkeys(FACTORS, 0) | dict(zip(factors, parts, strict=True))


def case(rng: random.Random) -> tuple[dict, dict]:
    factors = rng.sample(FACTORS, rng.randint(1, 4))
    values: dict = {"weights": _weights(rng, factors)}
    skills = rng.sample(SKILLS, 5)
    if "skills" in factors or rng.random() < 0.3:
        values["required_skills"] = skills[: rng.randint(0, 1)]
        values["preferred_skills"] = skills[1 : rng.randint(2, 4)]
    if "title" in factors:
        values["job_titles"] = rng.sample(TITLES, rng.randint(1, 2))
        values["seniority_preferences"] = rng.sample(SENIORITY, rng.randint(0, 1))
    if "location" in factors:
        values["locations"] = rng.sample(PLACES, rng.randint(0, 2))
        values["remote_policy"] = (
            rng.choice(["remote_only", "exclude_remote"])
            if not values["locations"]
            else rng.choice(["any", "remote_only"])
        )
    if "experience" in factors:
        values["experience_min_months"] = rng.choice([None, 12, 36])
        values["experience_max_months"] = (
            rng.choice([60, 96]) if values["experience_min_months"] is None else None
        )
    if "employment" in factors:
        values["employment_types"] = rng.sample(TYPES, rng.randint(1, 2))
    if "keywords" in factors:
        values["preferred_keywords"] = rng.sample(KEYWORDS, rng.randint(1, 3))
    if rng.random() < 0.2:
        values["excluded_keywords"] = [rng.choice(["Clearance", "Unpaid"])]
    has_body = rng.random() < 0.8
    mentioned = rng.sample(SKILLS, rng.randint(0, 5))
    job = {
        "title": f"{rng.choice(['', 'Senior ', 'Lead '])}{rng.choice(TITLES)}",
        "department": rng.choice([None, "Platform", "Data"]),
        "location_text": rng.choice([None, "Berlin, Germany", "Lisbon, PT", "Remote - Canada"]),
        "work_mode": rng.choice(MODES),
        "employment_type": rng.choice(JOB_TYPES),
        "description_text": (
            f"We build {' and '.join(mentioned)} systems. {rng.choice(KEYWORDS)} matter."
            + (" Security clearance needed." if rng.random() < 0.1 else "")
            if has_body
            else None
        ),
        "requirements_text": rng.choice(
            [None, "3+ years experience", "2-4 years", "5 years of SQL"]
        )
        if has_body
        else None,
        "confidence": rng.choice(["high", "medium", "low"]),
    }
    return values, job


def documents(count: int = 60, seed: int = 20261015) -> list[dict]:
    rng = random.Random(seed)
    results = []
    for _ in range(count):
        values, job = case(rng)
        results.append(
            {
                "criteria": values,
                "job": job,
                "result": to_document(score(Criteria.model_validate(values), JobFacts(**job))),
            }
        )
    return results


if __name__ == "__main__":
    print(json.dumps(documents(), sort_keys=True))
