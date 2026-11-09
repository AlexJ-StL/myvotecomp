"""Join, persist, and export the normalized election datasets."""

from collections.abc import Sequence
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from config import Settings, get_settings
from models import (
    CandidateVote,
    CandidateVoteData,
    DemographicRecord,
    DemographicRecordData,
    VoterRegistrationRecord,
    VoterRegistrationRecordData,
)

VOTE_COLUMNS = (
    "state_fips",
    "year",
    "office",
    "district",
    "party",
    "candidate_votes",
)
DEMOGRAPHIC_COLUMNS = (
    "state_fips",
    "year",
    "total_population",
    "working_age_18_64",
    "population_18_plus",
)
REGISTRATION_COLUMNS = (
    "state_fips",
    "year",
    "registered_voters",
    "republican_registrants",
    "democrat_registrants",
    "other_registrants",
)
EXPORT_COLUMNS = VOTE_COLUMNS + tuple(
    column
    for column in DEMOGRAPHIC_COLUMNS + REGISTRATION_COLUMNS
    if column not in {"state_fips", "year"}
)


def _dataframe(records: Sequence, columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.DataFrame(
        [record.model_dump(mode="json") for record in records],
        columns=columns,
    )
    frame["state_fips"] = frame["state_fips"].astype("string")
    frame["year"] = frame["year"].astype("Int64")
    return frame


def join_datasets(
    votes: Sequence[CandidateVoteData],
    demographics: Sequence[DemographicRecordData],
    registrations: Sequence[VoterRegistrationRecordData],
) -> pd.DataFrame:
    """Left-join dimension records onto votes using the full state-year key."""
    joined = _dataframe(votes, VOTE_COLUMNS)
    dimensions = (
        _dataframe(demographics, DEMOGRAPHIC_COLUMNS),
        _dataframe(registrations, REGISTRATION_COLUMNS),
    )
    for dimension in dimensions:
        joined = joined.merge(
            dimension,
            on=["state_fips", "year"],
            how="left",
            sort=False,
            validate="many_to_one",
        )
    return joined


def persist_records(
    engine: Engine,
    votes: Sequence[CandidateVoteData],
    demographics: Sequence[DemographicRecordData],
    registrations: Sequence[VoterRegistrationRecordData],
) -> None:
    """Persist all normalized source records atomically in one transaction."""
    with Session(engine) as session, session.begin():
        session.add_all(
            CandidateVote(**record.model_dump(mode="json")) for record in votes
        )
        session.add_all(
            DemographicRecord(**record.model_dump(mode="json"))
            for record in demographics
        )
        session.add_all(
            VoterRegistrationRecord(**record.model_dump(mode="json"))
            for record in registrations
        )


def export_dataset(data: pd.DataFrame, destination: str | Path) -> Path:
    """Write only the public analytical schema as CSV or Parquet."""
    path = Path(destination)
    safe_data = data.loc[:, [column for column in EXPORT_COLUMNS if column in data]]
    extension = path.suffix.lower()
    if extension == ".csv":
        safe_data.to_csv(path, index=False)
    elif extension == ".parquet":
        safe_data.to_parquet(path, index=False, engine="pyarrow")
    else:
        raise ValueError("Export destination must use a .csv or .parquet extension")
    return path


def build_engine(settings: Settings | None = None) -> Engine:
    """Create a PostgreSQL engine from runtime settings without logging secrets."""
    runtime_settings = settings or get_settings()
    return create_engine(runtime_settings.database_url, pool_pre_ping=True)


def run_pipeline(
    votes: Sequence[CandidateVoteData],
    demographics: Sequence[DemographicRecordData],
    registrations: Sequence[VoterRegistrationRecordData],
    *,
    engine: Engine,
    export_paths: Sequence[str | Path] = (),
) -> pd.DataFrame:
    """Join, persist, and optionally export one fully normalized pipeline batch."""
    joined = join_datasets(votes, demographics, registrations)
    persist_records(engine, votes, demographics, registrations)
    for path in export_paths:
        export_dataset(joined, path)
    return joined
