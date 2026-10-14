from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=100)
    bio: str = Field(default="", max_length=2000)

    @field_validator("display_name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Display name cannot be blank")
        return value.strip()
