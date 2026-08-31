import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import StatusEnum


# ---- Auth -------------------------------------------------------------
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    target_cities: list[str] = Field(default_factory=list, max_length=20)
    target_titles: str = Field(default="Software Engineer", max_length=500)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


WorkMode = Literal["", "remote", "hybrid", "onsite"]
Seniority = Literal["", "entry", "mid", "senior"]


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    target_cities: list[str]
    target_states: list[str]
    target_titles: str
    target_country: str
    work_mode: WorkMode
    seniority: Seniority
    min_salary: float | None
    address: str
    phone: str
    has_resume: bool

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    target_cities: list[str] | None = Field(default=None, max_length=20)
    # An empty list is "all states", so there is no cap worth setting below
    # the largest country's own count -- 51 for the US, plus headroom.
    target_states: list[str] | None = Field(default=None, max_length=60)
    target_titles: str | None = Field(default=None, max_length=500)
    target_country: str | None = Field(default=None, max_length=100)
    work_mode: WorkMode | None = None
    seniority: Seniority | None = None
    # 0 is a meaningful 'no floor' the UI can send when the box is cleared.
    min_salary: float | None = Field(default=None, ge=0, le=10_000_000)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=50)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class EmailChange(BaseModel):
    new_email: EmailStr
    # Required even though the caller is already authenticated: a token left
    # open on a shared machine shouldn't be enough to move the account to an
    # address the owner doesn't control.
    current_password: str


# ---- Resume -------------------------------------------------------------
class ResumeOut(BaseModel):
    filename: str
    skills: list[str]
    years_experience: float | None
    uploaded_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ---- Documents ---------------------------------------------------------
DocumentKind = Literal["resume", "cover_letter"]


class DocumentOut(BaseModel):
    id: int
    kind: DocumentKind
    label: str
    filename: str
    size_bytes: int
    created_at: datetime.datetime

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
    matches_preferences: bool
    mismatch_reason: str | None
    resume_document_id: int | None
    cover_letter_document_id: int | None
    status: StatusEnum
    notes: str

    model_config = ConfigDict(from_attributes=True)


class MatchUpdate(BaseModel):
    # 0 clears the link; None leaves it alone. Without the distinction there
    # is no way to say "detach" as opposed to "don't touch".
    resume_document_id: int | None = None
    cover_letter_document_id: int | None = None
    status: StatusEnum | None = None
    notes: str | None = None


class StatsOut(BaseModel):
    total: int
    avg_score: int
    applied: int
    interviewing: int
    offers: int


class JobSourceOut(BaseModel):
    """One entry in the board picker: a board and how many of its postings
    are in the window being asked about.

    The count is over the whole window, before any client-side filter such as
    "only my preferences" -- it answers "is there anything here", which is
    what a dropdown option needs to say.
    """

    name: str
    count: int


class CityOut(BaseModel):
    name: str
    job_count: int


class SubdivisionOut(BaseModel):
    code: str
    label: str
    job_count: int
    cities: list[CityOut]


class CountryOut(BaseModel):
    slug: str
    label: str
    subdivision_label: str
    """What this country calls the tier -- State, Province, Land, Nation,
    County. The picker uses it as its own label, because "State" over a list
    of Canadian provinces reads as a bug to anyone who lives there."""
    supports_postal_lookup: bool


class CountryDetailOut(CountryOut):
    subdivisions: list[SubdivisionOut]


class PostalLookupOut(BaseModel):
    """What a postal code resolved to, for filling in a profile address.

    Never used to filter jobs: no connector returns a postal code, so a
    postal-code job filter could only ever match nothing.
    """

    code: str
    label: str
    cities: list[str]
