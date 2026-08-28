import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import StatusEnum


# ---- Auth -------------------------------------------------------------
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    target_city: str = Field(default="Seattle, WA", max_length=255)
    target_titles: str = Field(default="Software Engineer", max_length=500)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


WorkMode = Literal["", "remote", "hybrid", "onsite"]


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    target_city: str
    target_titles: str
    target_country: str
    work_mode: WorkMode
    has_resume: bool

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    target_city: str | None = Field(default=None, max_length=255)
    target_titles: str | None = Field(default=None, max_length=500)
    target_country: str | None = Field(default=None, max_length=100)
    work_mode: WorkMode | None = None


# ---- Resume -------------------------------------------------------------
class ResumeOut(BaseModel):
    filename: str
    skills: list[str]
    years_experience: float | None
    uploaded_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ---- Jobs -------------------------------------------------------------
class JobOut(BaseModel):
    id: int
    title: str
    company: str
    location: str
    comp_min: float | None
    comp_max: float | None
    comp_unit: str
    job_type: str
    posted: str
    url: str
    skills: list[str]
    sources: list[str]
    score: int
    reason: str
    flag: str | None
    status: StatusEnum
    notes: str

    model_config = ConfigDict(from_attributes=True)


class MatchUpdate(BaseModel):
    status: StatusEnum | None = None
    notes: str | None = None


class StatsOut(BaseModel):
    total: int
    avg_score: int
    applied: int
    interviewing: int
    offers: int
