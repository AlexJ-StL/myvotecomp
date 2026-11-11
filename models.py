"""Validated data contracts and SQLAlchemy tables for election records."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

StateFips = Annotated[str, StringConstraints(pattern=r"^\d{2}$")]
NonNegativeInt = Annotated[int, Field(ge=0)]


class ElectionOffice(StrEnum):
    """Election offices supported by the pipeline."""

    HOUSE = "HOUSE"
    SENATE = "SENATE"
    GOVERNOR = "GOVERNOR"


class VoteParty(StrEnum):
    """Normalized candidate party groupings."""

    REPUBLICAN = "REPUBLICAN"
    DEMOCRAT = "DEMOCRAT"
    INDEPENDENT_OTHER = "INDEPENDENT_OTHER"


class RecordData(BaseModel):
    """Shared validation for records keyed by state and election year."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    state_fips: StateFips
    year: Annotated[int, Field(ge=0)]


class CandidateVoteData(RecordData):
    """A party-aggregated vote total for one state race."""

    office: ElectionOffice
    party: VoteParty
    district: str = ""
    candidate_votes: NonNegativeInt


class DemographicRecordData(RecordData):
    """State population totals and adult working-age counts."""

    total_population: NonNegativeInt
    working_age_18_64: NonNegativeInt
    population_18_plus: NonNegativeInt

    @model_validator(mode="after")
    def populations_are_ordered(self) -> DemographicRecordData:
        if self.working_age_18_64 > self.population_18_plus:
            raise ValueError("working-age population cannot exceed population age 18+")
        if self.population_18_plus > self.total_population:
            raise ValueError("population age 18+ cannot exceed total population")
        return self


class VoterRegistrationRecordData(RecordData):
    """State registration counts; party counts are null where uncollected."""

    registered_voters: NonNegativeInt
    republican_registrants: NonNegativeInt | None = None
    democrat_registrants: NonNegativeInt | None = None
    other_registrants: NonNegativeInt | None = None


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM records."""


class CandidateVote(Base):
    """Aggregated party votes persisted per state race and year."""

    __tablename__ = "candidate_votes"
    __table_args__ = (
        UniqueConstraint(
            "state_fips",
            "year",
            "office",
            "district",
            "party",
            name="uq_candidate_vote_race_party",
        ),
        CheckConstraint("length(state_fips) = 2", name="ck_candidate_vote_fips_length"),
        CheckConstraint("candidate_votes >= 0", name="ck_candidate_vote_nonnegative"),
        CheckConstraint(
            "office IN ('HOUSE', 'SENATE', 'GOVERNOR')",
            name="ck_candidate_vote_office",
        ),
        CheckConstraint(
            "party IN ('REPUBLICAN', 'DEMOCRAT', 'INDEPENDENT_OTHER')",
            name="ck_candidate_vote_party",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    office: Mapped[str] = mapped_column(String(16), nullable=False)
    district: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    party: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_votes: Mapped[int] = mapped_column(Integer, nullable=False)


class DemographicRecord(Base):
    """State demographic counts persisted once per year."""

    __tablename__ = "demographic_records"
    __table_args__ = (
        UniqueConstraint("state_fips", "year", name="uq_demographic_state_year"),
        CheckConstraint("length(state_fips) = 2", name="ck_demographic_fips_length"),
        CheckConstraint("total_population >= 0", name="ck_demographic_total_nonnegative"),
        CheckConstraint("working_age_18_64 >= 0", name="ck_demographic_working_age_nonnegative"),
        CheckConstraint("population_18_plus >= 0", name="ck_demographic_adult_nonnegative"),
        CheckConstraint(
            "working_age_18_64 <= population_18_plus",
            name="ck_demographic_age_bracket_order",
        ),
        CheckConstraint(
            "population_18_plus <= total_population",
            name="ck_demographic_total_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    total_population: Mapped[int] = mapped_column(Integer, nullable=False)
    working_age_18_64: Mapped[int] = mapped_column(Integer, nullable=False)
    population_18_plus: Mapped[int] = mapped_column(Integer, nullable=False)


class VoterRegistrationRecord(Base):
    """State registration counts with nullable partisan breakdowns."""

    __tablename__ = "voter_registration_records"
    __table_args__ = (
        UniqueConstraint("state_fips", "year", name="uq_registration_state_year"),
        CheckConstraint("length(state_fips) = 2", name="ck_registration_fips_length"),
        CheckConstraint("registered_voters >= 0", name="ck_registration_total_nonnegative"),
        CheckConstraint(
            "republican_registrants IS NULL OR republican_registrants >= 0",
            name="ck_registration_republican_nonnegative",
        ),
        CheckConstraint(
            "democrat_registrants IS NULL OR democrat_registrants >= 0",
            name="ck_registration_democrat_nonnegative",
        ),
        CheckConstraint(
            "other_registrants IS NULL OR other_registrants >= 0",
            name="ck_registration_other_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    registered_voters: Mapped[int] = mapped_column(Integer, nullable=False)
    republican_registrants: Mapped[int | None] = mapped_column(Integer)
    democrat_registrants: Mapped[int | None] = mapped_column(Integer)
    other_registrants: Mapped[int | None] = mapped_column(Integer)
