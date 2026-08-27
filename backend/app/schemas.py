import datetime
from pydantic import BaseModel, EmailStr, Field

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


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    target_city: str
    target_titles: str
    has_resume: bool

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    target_city: str | None = None
    target_titles: str | None = None


# ---- Resume -------------------------------------------------------------
class ResumeOut(BaseModel):
    filename: str
    skills: list[str]
    years_experience: float | None
    uploaded_at: datetime.datetime

    class Config:
        from_attributes = True


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
    score: int
    reason: str
    flag: str | None
    status: StatusEnum
    notes: str

    class Config:
        from_attributes = True


class MatchUpdate(BaseModel):
    status: StatusEnum | None = None
    notes: str | None = None


class StatsOut(BaseModel):
    total: int
    avg_score: int
    applied: int
    interviewing: int
    offers: int
