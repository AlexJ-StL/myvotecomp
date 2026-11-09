import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from models import (
    Base,
    CandidateVote,
    CandidateVoteData,
    DemographicRecord,
    DemographicRecordData,
    ElectionOffice,
    VoteParty,
    VoterRegistrationRecord,
    VoterRegistrationRecordData,
)
from pipeline import export_dataset, join_datasets, run_pipeline


def input_records() -> tuple[
    list[CandidateVoteData],
    list[DemographicRecordData],
    list[VoterRegistrationRecordData],
]:
    votes = [
        CandidateVoteData(
            state_fips="01",
            year=2024,
            office=ElectionOffice.HOUSE,
            district="1",
            party=VoteParty.REPUBLICAN,
            candidate_votes=100,
        ),
        CandidateVoteData(
            state_fips="28",
            year=2022,
            office=ElectionOffice.GOVERNOR,
            party=VoteParty.DEMOCRAT,
            candidate_votes=200,
        ),
    ]
    demographics = [
        DemographicRecordData(
            state_fips="01",
            year=2024,
            total_population=1_000,
            working_age_18_64=600,
            population_18_plus=800,
        ),
        DemographicRecordData(
            state_fips="01",
            year=2022,
            total_population=900,
            working_age_18_64=550,
            population_18_plus=700,
        ),
        DemographicRecordData(
            state_fips="28",
            year=2022,
            total_population=800,
            working_age_18_64=450,
            population_18_plus=650,
        ),
    ]
    registrations = [
        VoterRegistrationRecordData(
            state_fips="01",
            year=2024,
            registered_voters=700,
            republican_registrants=None,
            democrat_registrants=None,
            other_registrants=None,
        ),
        VoterRegistrationRecordData(
            state_fips="28",
            year=2022,
            registered_voters=500,
            republican_registrants=200,
            democrat_registrants=250,
            other_registrants=50,
        ),
    ]
    return votes, demographics, registrations


def test_join_uses_both_state_fips_and_year() -> None:
    votes, demographics, registrations = input_records()

    joined = join_datasets(votes, demographics, registrations)

    alabama = joined.loc[joined["state_fips"] == "01"].iloc[0]
    mississippi = joined.loc[joined["state_fips"] == "28"].iloc[0]
    assert len(joined) == 2
    assert alabama["year"] == 2024
    assert alabama["total_population"] == 1_000
    assert alabama["registered_voters"] == 700
    assert pd.isna(alabama["republican_registrants"])
    assert mississippi["year"] == 2022
    assert mississippi["total_population"] == 800
    assert mississippi["registered_voters"] == 500
    assert joined["candidate_votes"].sum() == 300


def test_join_rejects_duplicate_dimension_keys() -> None:
    votes, demographics, registrations = input_records()
    demographics.append(demographics[0])

    with pytest.raises(ValueError, match="many-to-one"):
        join_datasets(votes, demographics, registrations)


def test_run_pipeline_persists_records_and_exports_sanitized_csv_and_parquet(
    tmp_path,
) -> None:
    votes, demographics, registrations = input_records()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    csv_path = tmp_path / "election-export.csv"
    parquet_path = tmp_path / "election-export.parquet"

    joined = run_pipeline(
        votes,
        demographics,
        registrations,
        engine=engine,
        export_paths=[csv_path, parquet_path],
    )

    assert len(joined) == 2
    with Session(engine) as session:
        assert len(session.scalars(select(CandidateVote)).all()) == 2
        assert len(session.scalars(select(DemographicRecord)).all()) == 3
        persisted_registration = session.scalars(
            select(VoterRegistrationRecord).where(
                VoterRegistrationRecord.state_fips == "01"
            )
        ).one()
        assert persisted_registration.republican_registrants is None
        assert persisted_registration.democrat_registrants is None

    csv_data = pd.read_csv(csv_path)
    parquet_data = pd.read_parquet(parquet_path)
    assert csv_data.columns.tolist() == parquet_data.columns.tolist()
    assert "POSTGRES_PASSWORD" not in csv_data.columns
    assert "local_path" not in csv_data.columns
    assert csv_data["candidate_votes"].sum() == 300
    assert parquet_data["total_population"].sum() == 1_800


def test_export_drops_columns_outside_the_public_data_schema(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "state_fips": ["01"],
            "year": [2024],
            "candidate_votes": [100],
            "POSTGRES_PASSWORD": ["must-not-export"],
            "local_path": ["must-not-export"],
        }
    )
    path = tmp_path / "sanitized.csv"

    export_dataset(frame, path)

    exported = pd.read_csv(path, dtype={"state_fips": "string"})
    assert "POSTGRES_PASSWORD" not in exported.columns
    assert "local_path" not in exported.columns
    assert exported.loc[0, "state_fips"] == "01"
    assert exported.loc[0, "candidate_votes"] == 100
