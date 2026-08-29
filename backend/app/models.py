import datetime
import enum

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime.datetime:
    """Timezone-aware UTC now.

    `datetime.utcnow()` is deprecated from Python 3.12 and returns a naive
    datetime, which then silently compares wrong against aware ones.
    """
    return datetime.datetime.now(datetime.UTC)


class StatusEnum(str, enum.Enum):
    new = "new"
    saved = "saved"
    applied = "applied"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"
    archived = "archived"
    """Terminal "done with this" state, distinct from rejected.

    Rejected is something that happened to you; archived is a decision you
    made. Both end the pipeline, and the board groups them in one column, but
    collapsing them would throw away which of the two it was.
    """


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    target_cities: Mapped[list[str]] = mapped_column(JSON, default=list)
    """Cities the user will work in. Empty means anywhere.

    A list rather than a delimited string because a city is already written
    with a comma in it -- "Seattle, WA" -- so any separator that reads
    naturally is also ambiguous.
    """
    target_titles: Mapped[str] = mapped_column(String(500), default="Software Engineer")
    target_country: Mapped[str] = mapped_column(String(100), default="")
    """Free text, matched against a job's location by alias. Empty = anywhere."""

    seniority: Mapped[str] = mapped_column(String(20), default="")
    """"entry" | "mid" | "senior", or empty to derive it from the resume."""

    min_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Annual floor. NULL means no floor, which is distinct from a floor of 0."""

    address: Mapped[str] = mapped_column(String(500), default="")
    """Postal address. Profile data for applications -- scoring never reads it;
    target_city and target_country are what drive location matching."""

    phone: Mapped[str] = mapped_column(String(50), default="")
    """Contact number. Also profile-only, never used in scoring."""

    work_mode: Mapped[str] = mapped_column(String(20), default="")
    """"remote" | "hybrid" | "onsite", or empty for no preference.

    Deliberately a plain string rather than an Enum: the column takes a small
    closed set, but adding a second `str, enum.Enum` would trip the same
    UP042 lint that already blocks the dependency group, and Pydantic's
    Literal already rejects anything else at the API boundary.
    """
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    resume: Mapped["Resume | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    matches: Mapped[list["UserJobMatch"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    filename: Mapped[str] = mapped_column(String(255), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    years_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="resume")


class UserDocument(Base):
    """A resume or cover letter exactly as it was uploaded.

    The bytes are kept here, in the database, rather than on disk: Render's
    filesystem is ephemeral and render.yaml declares no persistent disk, so a
    file written to disk disappears on the next deploy -- which for "show me
    the resume I actually sent" is worse than not offering the feature. At a
    few hundred KB per document this is comfortable inside the free tier's
    1GB; object storage is the answer if that ever stops being true.

    Rows are immutable. Uploading a revision creates another row, because the
    point is to still have the version that was attached to an application
    six weeks ago.
    """

    __tablename__ = "user_documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    kind: Mapped[str] = mapped_column(String(20), default="resume")
    """"resume" | "cover_letter". A plain string rather than an Enum, matching
    work_mode and seniority -- Pydantic Literals guard the API boundary and a
    third str-Enum would trip the same UP042 lint."""

    label: Mapped[str] = mapped_column(String(120), default="")
    """What the user calls this version, e.g. "Backend-heavy, Oct"."""

    filename: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(100), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship()


class JobListing(Base):
    __tablename__ = "job_listings"
    __table_args__ = (
        # Dedup does an exact lookup on dedup_key, then a company-scoped fuzzy
        # pass over title_norm. This composite covers the second access pattern.
        Index("ix_job_listings_company_title", "company_norm", "title_norm"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    source: Mapped[str] = mapped_column(String(50), default="seed")
    """The first board this posting was seen on."""

    sources: Mapped[list[dict]] = mapped_column(JSON, default=list)
    """Every board it has been matched across: {name, external_id, url}."""

    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    """Namespaced as "<source>:<their id>" so it stays unique across boards."""

    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    comp_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    comp_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    comp_unit: Mapped[str] = mapped_column(String(20), default="year")  # "year" | "hour"
    job_type: Mapped[str] = mapped_column(String(50), default="Full-time")
    posted: Mapped[str] = mapped_column(String(20), default="")  # ISO date string
    url: Mapped[str] = mapped_column(String(1000), default="")
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    dedup_key: Mapped[str] = mapped_column(String(700), index=True, default="")
    company_norm: Mapped[str] = mapped_column(String(255), index=True, default="")
    title_norm: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserJobMatch(Base):
    __tablename__ = "user_job_matches"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_listings.id"), index=True)
    status: Mapped[StatusEnum] = mapped_column(Enum(StatusEnum), default=StatusEnum.new)
    notes: Mapped[str] = mapped_column(Text, default="")

    resume_document_id: Mapped[int | None] = mapped_column(ForeignKey("user_documents.id"), nullable=True)
    """Which resume version was actually sent for this application."""

    cover_letter_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_documents.id"), nullable=True
    )
    """And which cover letter, if any."""
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="matches")
    job: Mapped["JobListing"] = relationship()
    # Two FKs to the same table, so the join condition has to be spelled out.
    resume_document: Mapped["UserDocument | None"] = relationship(foreign_keys=[resume_document_id])
    cover_letter_document: Mapped["UserDocument | None"] = relationship(
        foreign_keys=[cover_letter_document_id]
    )
