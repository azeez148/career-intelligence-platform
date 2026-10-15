"""Pure deterministic matching. No I/O, clock, randomness, or catalogs.

The algorithm version must change whenever any rule below changes, so persisted matches
computed by an older rule set are rescored.
"""

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from app.modules.jobs.normalize import employment_type as employment_vocabulary
from app.modules.matching.text import JobText, TextIndex, tokens
from app.modules.preferences.schemas import Criteria

ALGORITHM_VERSION = "deterministic-1"
FACTORS = ("skills", "title", "location", "experience", "employment", "keywords")
SENIORITY_BONUS = Fraction(1, 5)
EXPERIENCE_DECAY_MONTHS = 24
YEARS = re.compile(
    r"\b(\d{1,2})\s*(\+|plus)?\s*(?:(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*)?(?:years?|yrs?)\b",
    re.IGNORECASE,
)
MAX_YEARS = 40


@dataclass(frozen=True)
class JobFacts:
    title: str
    department: str | None
    location_text: str | None
    work_mode: str
    employment_type: str
    description_text: str | None
    requirements_text: str | None
    confidence: str


@dataclass
class FactorResult:
    factor: str
    weight: int
    status: str  # matched | partial | not_matched | unknown
    score: Fraction | None
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    found_in: dict[str, str] = field(default_factory=dict)
    detail: dict[str, object] = field(default_factory=dict)
    contribution: Fraction | None = None


@dataclass(frozen=True)
class Exclusion:
    code: str
    values: tuple[str, ...] = ()


@dataclass
class MatchResult:
    status: str  # eligible | excluded | insufficient_information
    score: int | None
    coverage: Fraction
    factors: list[FactorResult]
    exclusions: list[Exclusion]
    flags: list[str]
    algorithm_version: str = ALGORITHM_VERSION


def _status(score: Fraction | None) -> str:
    if score is None:
        return "unknown"
    if score >= 1:
        return "matched"
    return "partial" if score > 0 else "not_matched"


def _found(text: JobText, values: list[str]) -> tuple[list[str], list[str], dict[str, str]]:
    matched: list[str] = []
    missing: list[str] = []
    where: dict[str, str] = {}
    for value in values:
        location = text.find(value)
        if location is None:
            missing.append(value)
        else:
            matched.append(value)
            where[value] = location
    return matched, missing, where


def skills_factor(criteria: Criteria, text: JobText, weight: int) -> FactorResult:
    required, preferred = criteria.required_skills, criteria.preferred_skills
    if not text.has_body:
        return FactorResult("skills", weight, "unknown", None, missing=[*required, *preferred])
    req_found, req_missing, req_where = _found(text, required)
    pref_found, pref_missing, pref_where = _found(text, preferred)
    total = 2 * len(required) + len(preferred)
    score = Fraction(2 * len(req_found) + len(pref_found), total) if total else None
    return FactorResult(
        "skills",
        weight,
        _status(score),
        score,
        [*req_found, *pref_found],
        [*req_missing, *pref_missing],
        req_where | pref_where,
        {"required_found": req_found, "required_missing": req_missing},
    )


def title_factor(criteria: Criteria, job: JobFacts, weight: int) -> FactorResult:
    title = TextIndex(job.title)
    title_set = set(title.tokens)
    contained = [value for value in criteria.job_titles if title.contains(tokens(value))]
    best = Fraction(1) if contained else Fraction(0)
    closest: str | None = contained[0] if contained else None
    for value in criteria.job_titles if not contained else []:
        phrase = set(tokens(value))
        union = title_set | phrase
        similarity = Fraction(len(title_set & phrase), len(union)) if union else Fraction(0)
        if similarity > best:
            best, closest = similarity, value
    seniority = [value for value in criteria.seniority_preferences if title.contains(tokens(value))]
    if criteria.job_titles:
        score = min(Fraction(1), best + (SENIORITY_BONUS if seniority else 0))
    else:
        score = Fraction(1) if seniority else Fraction(0)
    matched = contained[:1] + seniority
    missing = [] if contained else list(criteria.job_titles)
    if criteria.seniority_preferences and not seniority:
        missing += criteria.seniority_preferences
    return FactorResult(
        "title",
        weight,
        _status(score),
        score,
        matched,
        missing,
        dict.fromkeys(matched, "title"),
        {"closest_title": closest, "title_similarity": str(best), "seniority_found": seniority},
    )


def location_factor(criteria: Criteria, job: JobFacts, weight: int) -> FactorResult:
    place = TextIndex(job.location_text)
    found = [value for value in criteria.locations if place.contains(tokens(value))]
    detail: dict[str, object] = {
        "work_mode": job.work_mode,
        "remote_policy": criteria.remote_policy,
    }
    score: Fraction | None
    if criteria.locations:
        # Geographic restrictions still apply to remote roles; without location text they
        # cannot be checked either way.
        score = (Fraction(1) if found else Fraction(0)) if place else None
    elif criteria.remote_policy == "remote_only":
        score = None if job.work_mode == "unknown" else Fraction(int(job.work_mode == "remote"))
    elif criteria.remote_policy == "exclude_remote":
        score = None if job.work_mode == "unknown" else Fraction(int(job.work_mode != "remote"))
    else:
        score = None
    missing = [] if found or score is None else list(criteria.locations)
    return FactorResult(
        "location",
        weight,
        _status(score),
        score,
        found,
        missing,
        dict.fromkeys(found, "location"),
        detail,
    )


def required_years(text: str | None) -> tuple[int, int | None] | None:
    """The most demanding explicit 'N years' / 'N+ years' / 'N–M years' statement."""
    if not text:
        return None
    best: tuple[int, int | None] | None = None
    for match in YEARS.finditer(text[:200_000]):
        low = int(match.group(1))
        high = int(match.group(3)) if match.group(3) else None
        if low > MAX_YEARS or (high is not None and (high < low or high > MAX_YEARS)):
            continue
        if best is None or low > best[0]:
            best = (low, high)
    return best


def experience_factor(criteria: Criteria, job: JobFacts, weight: int) -> FactorResult:
    stated = required_years(job.requirements_text or job.description_text)
    if stated is None:
        return FactorResult("experience", weight, "unknown", None)
    low, high = stated[0] * 12, (stated[1] if stated[1] is not None else stated[0]) * 12
    user_low = criteria.experience_min_months or 0
    user_high = criteria.experience_max_months
    if user_high is not None and low > user_high:
        gap = low - user_high
    elif high < user_low:
        gap = user_low - high
    else:
        gap = 0
    score = max(Fraction(0), 1 - Fraction(gap, EXPERIENCE_DECAY_MONTHS))
    label = f"{stated[0]}–{stated[1]} years" if stated[1] is not None else f"{stated[0]}+ years"
    return FactorResult(
        "experience",
        weight,
        _status(score),
        score,
        [label] if score == 1 else [],
        [] if score == 1 else [label],
        {},
        {"job_years": list(stated), "gap_months": gap},
    )


def employment_factor(criteria: Criteria, job: JobFacts, weight: int) -> FactorResult:
    wanted = {employment_vocabulary(value) for value in criteria.employment_types} - {"unknown"}
    unrecognized = [v for v in criteria.employment_types if employment_vocabulary(v) == "unknown"]
    detail: dict[str, object] = {"job_type": job.employment_type, "unrecognized": unrecognized}
    if not wanted or job.employment_type == "unknown":
        return FactorResult("employment", weight, "unknown", None, detail=detail)
    score = Fraction(int(job.employment_type in wanted))
    matched = [
        v for v in criteria.employment_types if employment_vocabulary(v) == job.employment_type
    ]
    missing = [] if matched else [v for v in criteria.employment_types if v not in unrecognized]
    return FactorResult("employment", weight, _status(score), score, matched, missing, {}, detail)


def keywords_factor(criteria: Criteria, text: JobText, weight: int) -> FactorResult:
    if not text.has_body:
        return FactorResult(
            "keywords", weight, "unknown", None, missing=list(criteria.preferred_keywords)
        )
    found, missing, where = _found(text, criteria.preferred_keywords)
    total = len(criteria.preferred_keywords)
    score = Fraction(len(found), total) if total else None
    return FactorResult("keywords", weight, _status(score), score, found, missing, where)


def exclusions(criteria: Criteria, job: JobFacts, text: JobText) -> list[Exclusion]:
    found: list[Exclusion] = []
    excluded = [value for value in criteria.excluded_keywords if text.find(value)]
    if excluded:
        found.append(Exclusion("excluded_keyword", tuple(excluded)))
    if criteria.remote_policy == "remote_only" and job.work_mode in {"hybrid", "onsite"}:
        found.append(Exclusion("not_remote", (job.work_mode,)))
    if criteria.remote_policy == "exclude_remote" and job.work_mode == "remote":
        found.append(Exclusion("remote_excluded", ("remote",)))
    if criteria.required_skills and text.has_body:
        _, missing, _ = _found(text, criteria.required_skills)
        if missing:
            found.append(Exclusion("missing_required_skill", tuple(missing)))
    return found


def round_half_up(value: Fraction) -> int:
    return int((Decimal(value.numerator) / Decimal(value.denominator)).quantize(0, ROUND_HALF_UP))


def score(criteria: Criteria, job: JobFacts) -> MatchResult:
    text = JobText(job.title, job.department, job.description_text, job.requirements_text)
    weights = criteria.weights.model_dump()
    builders = {
        "skills": lambda w: skills_factor(criteria, text, w),
        "title": lambda w: title_factor(criteria, job, w),
        "location": lambda w: location_factor(criteria, job, w),
        "experience": lambda w: experience_factor(criteria, job, w),
        "employment": lambda w: employment_factor(criteria, job, w),
        "keywords": lambda w: keywords_factor(criteria, text, w),
    }
    factors = [builders[name](weights[name]) for name in FACTORS if weights[name] > 0]
    known = [factor for factor in factors if factor.score is not None]
    known_weight = sum(factor.weight for factor in known)
    flags: list[str] = []
    if criteria.required_skills and not text.has_body:
        flags.append("required_skills_unverified")
    if job.confidence == "low":
        flags.append("low_confidence_source")
    coverage = Fraction(known_weight, 100)
    if coverage < Fraction(1, 2):
        flags.append("limited_information")
    blocked = exclusions(criteria, job, text)
    if known_weight == 0:
        return MatchResult("insufficient_information", None, coverage, factors, blocked, flags)
    total = sum((Fraction(f.weight) * f.score for f in known if f.score is not None), Fraction(0))
    for factor in known:
        assert factor.score is not None
        factor.contribution = Fraction(100 * factor.weight) * factor.score / known_weight
    if blocked:
        return MatchResult("excluded", 0, coverage, factors, blocked, flags)
    return MatchResult(
        "eligible", round_half_up(100 * total / known_weight), coverage, factors, blocked, flags
    )
