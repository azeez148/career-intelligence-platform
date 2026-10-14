from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.core.urls import source_url
from app.core.values import display_text


class CompanyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=200)
    website_url: str | None = Field(default=None, max_length=2048)
    careers_url: str | None = Field(default=None, max_length=2048)

    @field_validator("name", mode="before")
    @classmethod
    def valid_name(cls, value: object) -> object:
        if isinstance(value, str):
            value = display_text(value)
            if not value:
                raise PydanticCustomError("blank_value", "Name cannot be blank")
        return value

    @field_validator("website_url", "careers_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return source_url(value)
        except ValueError:
            raise PydanticCustomError("source_url", "Invalid source URL") from None

    @model_validator(mode="after")
    def has_identity(self) -> Self:
        if not any((self.name, self.website_url, self.careers_url)):
            raise PydanticCustomError("company_identity", "Supply a name or URL")
        return self


class CompanyView(CompanyInput):
    id: UUID
    display_label: str
    source_status: Literal["unverified"] = "unverified"
    created_at: datetime
    updated_at: datetime


class CompanyPage(BaseModel):
    items: list[CompanyView]
    next_offset: int | None
