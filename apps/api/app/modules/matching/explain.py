"""Template explanations for deterministic match results. No AI is involved."""

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Any

from app.modules.matching.scoring import Exclusion, FactorResult, MatchResult

FACTOR_LABELS = {
    "skills": "skills",
    "title": "job title",
    "location": "location",
    "experience": "experience",
    "employment": "employment type",
    "keywords": "keywords",
}
EXCLUSION_TEXT = {
    "excluded_keyword": "Mentions an excluded keyword: {values}.",
    "not_remote": "You asked for remote roles only; this job is {values}.",
    "remote_excluded": "You excluded remote roles; this job is remote.",
    "missing_required_skill": "A required skill is not mentioned: {values}.",
}
FLAG_TEXT = {
    "required_skills_unverified": (
        "Required skills could not be checked: the job has no description."
    ),
    "low_confidence_source": "Job details were inferred from page layout and may be incomplete.",
    "limited_information": "Less than half of your weighting could be evaluated for this job.",
}
FIELD_TEXT = {"title": "title", "requirements": "requirements", "description": "description",
              "department": "department", "location": "location"}  # fmt: skip


def _list(values: list[str] | tuple[str, ...]) -> str:
    return ", ".join(values)


def _decimal(value: Fraction | None, places: int = 4) -> str | None:
    if value is None:
        return None
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    return str(exact.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP))


def factor_sentence(factor: FactorResult) -> str:
    label = FACTOR_LABELS[factor.factor]
    if factor.status == "unknown":
        if factor.factor == "employment" and factor.detail.get("job_type") != "unknown":
            return "None of your employment types are recognized values, so this was not scored."
        return f"The job does not state enough to evaluate {label}; this factor was left out."
    if factor.factor == "skills" or factor.factor == "keywords":
        total = len(factor.matched) + len(factor.missing)
        where = sorted({FIELD_TEXT[factor.found_in[value]] for value in factor.matched})
        text = f"Found {len(factor.matched)} of {total} {label}"
        if factor.matched:
            text += f" in the {' and '.join(where)}: {_list(factor.matched)}"
        text += "."
        if factor.missing:
            text += f" Not found: {_list(factor.missing)}."
        return text
    if factor.factor == "title":
        if factor.status == "matched":
            return f"The job title matches {_list(factor.matched)}."
        closest = factor.detail.get("closest_title")
        if closest:
            return f"The job title partly resembles {closest}."
        return "The job title does not match your titles."
    if factor.factor == "location":
        if factor.matched:
            return f"The location mentions {_list(factor.matched)}."
        if factor.detail.get("remote_policy") != "any" and not factor.missing:
            return f"The work mode ({factor.detail['work_mode']}) fits your remote preference."
        return f"The location does not mention {_list(factor.missing)}."
    if factor.factor == "experience":
        stated = (factor.matched or factor.missing)[0]
        if factor.status == "matched":
            return f"Asks for {stated}, within your experience range."
        return f"Asks for {stated}, {factor.detail['gap_months']} months outside your range."
    if factor.factor == "employment":
        if factor.matched:
            return f"Employment type matches {_list(factor.matched)}."
        job_type = str(factor.detail["job_type"]).replace("_", "-")
        return f"Employment type is {job_type}, not one you selected."
    return ""


def exclusion_sentence(exclusion: Exclusion) -> str:
    return EXCLUSION_TEXT[exclusion.code].format(values=_list(exclusion.values))


def summary(result: MatchResult) -> str:
    if result.status == "excluded":
        return exclusion_sentence(result.exclusions[0])
    if result.status == "insufficient_information":
        return "The job does not state enough to evaluate any weighted preference."
    strongest = max(
        (f for f in result.factors if f.contribution is not None),
        key=lambda f: f.contribution or 0,
        default=None,
    )
    if strongest is None or not strongest.contribution:
        return "None of your weighted preferences matched."
    return f"Strongest match: {FACTOR_LABELS[strongest.factor]}."


def to_document(result: MatchResult) -> dict[str, Any]:
    """JSON-safe, exact (decimal string) representation persisted with each match."""
    return {
        "algorithm_version": result.algorithm_version,
        "status": result.status,
        "score": result.score,
        "coverage": _decimal(result.coverage),
        "summary": summary(result),
        "flags": [{"code": flag, "text": FLAG_TEXT[flag]} for flag in result.flags],
        "exclusions": [
            {"code": e.code, "values": list(e.values), "text": exclusion_sentence(e)}
            for e in result.exclusions
        ],
        "factors": [
            {
                "factor": f.factor,
                "weight": f.weight,
                "status": f.status,
                "score": _decimal(f.score),
                "contribution": _decimal(f.contribution, 2),
                "matched": f.matched,
                "missing": f.missing,
                "found_in": f.found_in,
                "text": factor_sentence(f),
            }
            for f in result.factors
        ],
    }
