import datetime
import enum

from sqlalchemy import (
    Column, Integer, String, Float, Text, ForeignKey, DateTime, Enum, UniqueConstraint, JSON
)
from sqlalchemy.orm import relationship

from .database import Base


class StatusEnum(str, enum.Enum):
    new = "new"
    saved = "saved"
    applied = "applied"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False, default="")
    hashed_password = Column(String(255), nullable=False)
    target_city = Column(String(255), nullable=False, default="Seattle, WA")
    target_titles = Column(String(500), nullable=False, default="Software Engineer")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    resume = relationship("Resume", back_populates="user", uselist=False, cascade="all, delete-orphan")
    matches = relationship("UserJobMatch", back_populates="user", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    filename = Column(String(255), nullable=False, default="")
    raw_text = Column(Text, nullable=False, default="")
    skills = Column(JSON, nullable=False, default=list)  # list[str] canonical skill tags
    years_experience = Column(Float, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="resume")


class JobListing(Base):
    __tablename__ = "job_listings"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False, default="seed")  # "adzuna" | "seed"
    external_id = Column(String(255), unique=True, index=True, nullable=False)
    title = Column(String(500), nullable=False)
    company = Column(String(255), nullable=False, default="")
    location = Column(String(255), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    comp_min = Column(Float, nullable=True)
    comp_max = Column(Float, nullable=True)
    comp_unit = Column(String(20), nullable=False, default="year")  # "year" | "hour"
    job_type = Column(String(50), nullable=False, default="Full-time")
    posted = Column(String(20), nullable=False, default="")  # ISO date string
    url = Column(String(1000), nullable=False, default="")
    skills = Column(JSON, nullable=False, default=list)  # list[str] canonical skill tags
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class UserJobMatch(Base):
    __tablename__ = "user_job_matches"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("job_listings.id"), nullable=False)
    status = Column(Enum(StatusEnum), nullable=False, default=StatusEnum.new)
    notes = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="matches")
    job = relationship("JobListing")
