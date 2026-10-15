import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from app.modules.matching.explain import to_document
from app.modules.matching.scoring import JobFacts, required_years, score
from app.modules.matching.text import JobText, tokens
from app.modules.preferences.schemas import Criteria

ZERO_WEIGHTS = dict.fromkeys(
    ("skills", "title", "location", "experience", "employment", "keywords"), 0
)


def criteria(weights: dict[str, int], **values) -> Criteria:
    return Criteria.model_validate({**values, "weights": ZERO_WEIGHTS | weights})


def job(**values) -> JobFacts:
    defaults = {
        "title": "Senior Backend Engineer",
        "department": "Platform",
        "location_text": "Berlin, Germany",
        "work_mode": "hybrid",
        "employment_type": "full_time",
        "description_text": "Build APIs with Python and PostgreSQL. Node.js is a plus.",
        "requirements_text": "- 3+ years of Python\n- Experience with C++ or C#",
        "confidence": "high",
    }
    return JobFacts(**(defaults | values))


def test_tokens_are_catalog_free_and_symbol_aware():
    assert tokens("Node.js") == tokens("node js") == ("node", "js")
    assert tokens("full-time") == tokens("Full Time")
    assert tokens("C++ and C#") == ("c++", "and", "c#")
    assert tokens("Experience with .NET") == ("experience", "with", ".net")
    assert tokens("ＰＹＴＨＯＮ") == ("python",)  # NFKC full-width
    assert tokens("APIs") != tokens("API")  # no plural or synonym inference
    text = JobText("Engineer", None, "We use Kubernetes daily", None)
    assert text.find("kubernetes") == "description" and text.find("kube") is None
    assert text.find("Engineer") == "title"


def test_exact_match_scores_100_with_full_coverage():
    result = score(
        criteria(
            {
                "skills": 40,
                "title": 20,
                "location": 10,
                "experience": 10,
                "employment": 10,
                "keywords": 10,
            },
            preferred_skills=["Python", "PostgreSQL"],
            required_skills=["C++"],
            job_titles=["Backend Engineer"],
            locations=["Berlin"],
            experience_min_months=36,
            employment_types=["Full-time"],
            preferred_keywords=["APIs"],
        ),
        job(),
    )
    assert (result.status, result.score, result.coverage) == ("eligible", 100, Fraction(1))
    assert {f.factor: f.status for f in result.factors} == dict.fromkeys(
        ("skills", "title", "location", "experience", "employment", "keywords"), "matched"
    )
    document = to_document(result)
    skills = next(f for f in document["factors"] if f["factor"] == "skills")
    assert skills["text"] == (
        "Found 3 of 3 skills in the description and requirements: C++, Python, PostgreSQL."
    )
    assert document["coverage"] == "1.0000" and document["summary"] == "Strongest match: skills."


def test_partial_match_is_hand_computed():
    # skills: 1 of 2 preferred found = 1/2 at weight 50; title contained = 1 at weight 50 → 75.
    result = score(
        criteria(
            {"skills": 50, "title": 50},
            preferred_skills=["Python", "Go"],
            job_titles=["Backend Engineer"],
        ),
        job(),
    )
    assert result.score == 75
    skills = to_document(result)["factors"][0]
    assert skills["status"] == "partial" and skills["missing"] == ["Go"]
    assert skills["contribution"] == "25.00"


def test_required_skills_gate_only_when_text_can_be_checked():
    wanted = criteria({"skills": 100}, required_skills=["Rust"], preferred_skills=["Python"])
    excluded = score(wanted, job())
    assert (excluded.status, excluded.score) == ("excluded", 0)
    assert [(e.code, e.values) for e in excluded.exclusions] == [
        ("missing_required_skill", ("Rust",))
    ]
    assert to_document(excluded)["summary"] == "A required skill is not mentioned: Rust."

    no_text = score(wanted, job(description_text=None, requirements_text=None))
    assert no_text.status == "insufficient_information" and no_text.score is None
    assert "required_skills_unverified" in no_text.flags and no_text.exclusions == []


@pytest.mark.parametrize(
    ("policy", "work_mode", "excluded"),
    [
        ("remote_only", "remote", False),
        ("remote_only", "hybrid", True),
        ("remote_only", "onsite", True),
        ("remote_only", "unknown", False),
        ("exclude_remote", "remote", True),
        ("exclude_remote", "onsite", False),
        ("exclude_remote", "unknown", False),
        ("any", "remote", False),
    ],
)
def test_remote_policy_exclusions(policy, work_mode, excluded):
    weights = {"title": 100} if policy == "any" else {"location": 50, "title": 50}
    result = score(
        criteria(weights, job_titles=["Backend Engineer"], remote_policy=policy),
        job(work_mode=work_mode),
    )
    assert (result.status == "excluded") is excluded


def test_location_requires_text_even_for_remote_roles():
    wanted = criteria({"location": 100}, locations=["Germany"], remote_policy="remote_only")
    assert score(wanted, job(work_mode="remote")).score == 100
    assert score(wanted, job(work_mode="remote", location_text="Remote, Canada")).score == 0
    unknown = score(wanted, job(work_mode="remote", location_text=None))
    assert unknown.status == "insufficient_information"


def test_missing_information_is_renormalized_and_reported():
    wanted = criteria(
        {"skills": 60, "experience": 40}, preferred_skills=["Python"], experience_min_months=12
    )
    result = score(wanted, job(requirements_text="Python every day", description_text="Team"))
    assert result.score == 100 and result.coverage == Fraction(3, 5)
    experience = next(f for f in to_document(result)["factors"] if f["factor"] == "experience")
    assert experience["status"] == "unknown" and "left out" in experience["text"]
    sparse = score(
        criteria(
            {"skills": 30, "experience": 70}, preferred_skills=["Python"], experience_min_months=12
        ),
        job(requirements_text="Python"),
    )
    assert "limited_information" in sparse.flags


def test_weight_changes_change_the_score():
    values = {"preferred_skills": ["Python", "Go"], "job_titles": ["Data Scientist"]}
    first = score(criteria({"skills": 80, "title": 20}, **values), job())
    second = score(criteria({"skills": 20, "title": 80}, **values), job())
    assert first.score is not None and second.score is not None and first.score > second.score


def test_rounding_is_half_up_and_bounds_hold():
    # skills 1/2 at weight 25 = 12.5 points; title 0 at weight 75 → 12.5 rounds to 13.
    half = score(
        criteria(
            {"skills": 25, "title": 75}, preferred_skills=["Python", "Go"], job_titles=["Chef"]
        ),
        job(),
    )
    assert half.score == 13
    nothing = score(criteria({"title": 100}, job_titles=["Pastry Chef"]), job())
    assert (nothing.status, nothing.score) == ("eligible", 0)


def test_experience_parsing_and_decay():
    assert required_years("3+ years Python; 5 years overall") == (5, None)
    assert required_years("3-5 years") == (3, 5)
    assert required_years("Founded 120 years ago, 2 yrs exp") == (2, None)
    assert required_years("Several years") is None
    wanted = lambda **months: criteria({"experience": 100}, **months)  # noqa: E731
    five_plus = job(requirements_text="5+ years required")
    assert score(wanted(experience_max_months=60), five_plus).score == 100
    assert score(wanted(experience_max_months=48), five_plus).score == 50
    assert score(wanted(experience_max_months=36), five_plus).score == 0
    assert score(wanted(experience_min_months=72), job(requirements_text="3–5 years")).score == 50


def test_employment_type_uses_the_shared_vocabulary():
    assert score(criteria({"employment": 100}, employment_types=["Full-time"]), job()).score == 100
    assert score(criteria({"employment": 100}, employment_types=["Contract"]), job()).score == 0
    unknown = score(
        criteria({"employment": 100}, employment_types=["Full-time"]),
        job(employment_type="unknown"),
    )
    assert unknown.status == "insufficient_information"
    unrecognized = score(criteria({"employment": 100}, employment_types=["Seasonal"]), job())
    assert unrecognized.status == "insufficient_information"


def test_excluded_keywords_match_any_field_and_low_confidence_is_flagged():
    result = score(
        criteria({"title": 100}, job_titles=["Backend Engineer"], excluded_keywords=["Senior"]),
        job(confidence="low"),
    )
    assert result.status == "excluded" and result.exclusions[0].values == ("Senior",)
    assert "low_confidence_source" in result.flags


def test_golden_cases_are_reproducible_in_process():
    from matching_cases import GOLDEN, documents

    assert documents() == json.loads(GOLDEN.read_text())


@pytest.mark.parametrize("hash_seed", ["1", "4242"])
def test_golden_cases_are_reproducible_across_interpreters(hash_seed):
    from matching_cases import GOLDEN

    result = subprocess.run(
        [sys.executable, "tests/matching_cases.py"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": "."},
        cwd=Path(__file__).parents[1],
        check=True,
    )
    assert json.loads(result.stdout) == json.loads(GOLDEN.read_text())
