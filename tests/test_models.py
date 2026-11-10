import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    Base,
    CandidateVote,
    CandidateVoteData,
    DemographicRecordData,
    ElectionOffice,
    VoteParty,
    VoterRegistrationRecordData,
)


def valid_vote_data(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "state_fips": "01",
        "year": 2024,
        "office": ElectionOffice.HOUSE,
        "party": VoteParty.REPUBLICAN,
        "candidate_votes": 125,
    }
    values.update(overrides)
    return values


def test_candidate_vote_accepts_valid_state_office_party_and_votes() -> None:
    vote = CandidateVoteData(**valid_vote_data())

    assert vote.state_fips == "01"
    assert vote.office is ElectionOffice.HOUSE
    assert vote.party is VoteParty.REPUBLICAN
    assert vote.candidate_votes == 125


def test_state_fips_must_be_two_numeric_characters() -> None:
    for invalid_fips in ("1", "001", "AA", "A1"):
        with pytest.raises(ValidationError):
            CandidateVoteData(**valid_vote_data(state_fips=invalid_fips))


def test_candidate_votes_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        CandidateVoteData(**valid_vote_data(candidate_votes=-1))


def test_office_is_limited_to_house_senate_or_governor() -> None:
    for office in ElectionOffice:
        assert CandidateVoteData(**valid_vote_data(office=office)).office is office

    with pytest.raises(ValidationError):
        CandidateVoteData(**valid_vote_data(office="PRESIDENT"))


def test_demographic_and_registration_metrics_validate_nonnegative_counts() -> None:
    demographic = DemographicRecordData(
        state_fips="28",
        year=2024,
        total_population=2_900_000,
        working_age_18_64=1_700_000,
        population_18_plus=2_200_000,
    )
    registration = VoterRegistrationRecordData(
        state_fips="28",
        year=2024,
        registered_voters=1_500_000,
        republican_registrants=None,
        democrat_registrants=None,
        other_registrants=None,
    )

    assert demographic.working_age_18_64 == 1_700_000
    assert registration.republican_registrants is None
    with pytest.raises(ValidationError):
        DemographicRecordData(
            state_fips="28",
            year=2024,
            total_population=-1,
            working_age_18_64=0,
            population_18_plus=0,
        )
    with pytest.raises(ValidationError):
        VoterRegistrationRecordData(
            state_fips="28",
            year=2024,
            registered_voters=-1,
        )


def test_demographic_populations_must_be_consistently_ordered() -> None:
    with pytest.raises(ValidationError, match="working-age population"):
        DemographicRecordData(
            state_fips="01",
            year=2024,
            total_population=100,
            working_age_18_64=81,
            population_18_plus=80,
        )

    with pytest.raises(
        ValidationError, match=r"population age 18\+ cannot exceed total"
    ):
        DemographicRecordData(
            state_fips="01",
            year=2024,
            total_population=100,
            working_age_18_64=70,
            population_18_plus=101,
        )


def test_sqlalchemy_schema_enforces_vote_and_office_constraints() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            CandidateVote(
                state_fips="01",
                year=2024,
                office="HOUSE",
                party="REPUBLICAN",
                candidate_votes=-1,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

        session.add(
            CandidateVote(
                state_fips="01",
                year=2024,
                office="PRESIDENT",
                party="REPUBLICAN",
                candidate_votes=10,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
