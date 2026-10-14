from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.core.values import comparison_key, display_text


def nonblank(value: str) -> str:
    value = display_text(value)
    if not value:
        raise PydanticCustomError("blank_value", "Value cannot be blank")
    return value


TextValue = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(nonblank)]
Weight = Annotated[int, Field(strict=True, ge=0, le=100)]
Months = Annotated[int, Field(strict=True, ge=0, le=1200)]


def unique_values(values: list[str]) -> list[str]:
    if len({comparison_key(value) for value in values}) != len(values):
        raise PydanticCustomError("duplicate_values", "List entries must be distinct")
    return values


Values = Annotated[list[TextValue], Field(max_length=50), AfterValidator(unique_values)]


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skills: Weight
    title: Weight
    location: Weight
    experience: Weight
    employment: Weight
    keywords: Weight

    @model_validator(mode="after")
    def allocation(self) -> Self:
        if sum(self.model_dump().values()) != 100:
            raise PydanticCustomError("weight_total", "Weights must total 100")
        return self


class Criteria(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preferred_skills: Values = Field(default_factory=list)
    required_skills: Values = Field(default_factory=list)
    preferred_keywords: Values = Field(default_factory=list)
    excluded_keywords: Values = Field(default_factory=list)
    job_titles: Values = Field(default_factory=list)
    seniority_preferences: Values = Field(default_factory=list)
    locations: Values = Field(default_factory=list)
    employment_types: Values = Field(default_factory=list)
    remote_policy: Literal["any", "remote_only", "exclude_remote"] = "any"
    experience_min_months: Months | None = None
    experience_max_months: Months | None = None
    weights: Weights

    @model_validator(mode="after")
    def consistent(self) -> Self:
        lists = (
            self.preferred_skills,
            self.required_skills,
            self.preferred_keywords,
            self.excluded_keywords,
            self.job_titles,
            self.seniority_preferences,
            self.locations,
            self.employment_types,
        )
        if sum(map(len, lists)) > 200:
            raise PydanticCustomError("too_many_values", "Use at most 200 total list entries")
        keys = [{comparison_key(value) for value in values} for values in lists]
        if keys[0] & keys[1] or keys[3] & (keys[0] | keys[1] | keys[2] | keys[4]):
            raise PydanticCustomError("preference_conflict", "Preference values conflict")
        if (
            self.experience_min_months is not None
            and self.experience_max_months is not None
            and self.experience_min_months > self.experience_max_months
        ):
            raise PydanticCustomError("experience_range", "Minimum exceeds maximum experience")
        configured = {
            "skills": bool(self.preferred_skills or self.required_skills),
            "title": bool(self.job_titles or self.seniority_preferences),
            "location": bool(self.locations or self.remote_policy != "any"),
            "experience": self.experience_min_months is not None
            or self.experience_max_months is not None,
            "employment": bool(self.employment_types),
            "keywords": bool(self.preferred_keywords),
        }
        if any(
            weight > 0 and not configured[factor]
            for factor, weight in self.weights.model_dump().items()
        ):
            raise PydanticCustomError("weight_without_criteria", "Positive weights need criteria")
        return self


class PreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: TextValue
    criteria: Criteria


class PreferenceSummary(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class PreferenceView(PreferenceSummary):
    criteria: Criteria


class PreferencePage(BaseModel):
    items: list[PreferenceSummary]
    next_offset: int | None
