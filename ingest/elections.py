"""CSV ingestion and party aggregation for state election results."""

import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

from ingest.geography import normalize_state_fips
from models import CandidateVoteData, ElectionOffice, VoteParty

_REPUBLICAN_ALIASES = {"R", "REP", "REPUBLICAN", "GOP"}
_DEMOCRAT_ALIASES = {"D", "DEM", "DEMOCRAT", "DEMOCRATIC", "DFL"}


def normalize_party(value: object) -> VoteParty:
    """Map source party labels into the pipeline's three neutral groups."""
    label = str(value or "").strip().upper()
    if label in _REPUBLICAN_ALIASES:
        return VoteParty.REPUBLICAN
    if label in _DEMOCRAT_ALIASES:
        return VoteParty.DEMOCRAT
    return VoteParty.INDEPENDENT_OTHER


def _normalize_office(value: object) -> ElectionOffice | None:
    office = str(value or "").strip().upper()
    if "HOUSE" in office:
        return ElectionOffice.HOUSE
    if "SENATE" in office:
        return ElectionOffice.SENATE
    if "GOVERNOR" in office or office in {"GOV", "GOVERNOR"}:
        return ElectionOffice.GOVERNOR
    return None


def _row_value(row: dict[str, str], *names: str) -> str:
    normalized = {
        key.strip().lower().replace(" ", "_"): value
        for key, value in row.items()
        if key
    }
    for name in names:
        value = normalized.get(name)
        if value is not None:
            return value.strip()
    raise ValueError(f"Election CSV is missing required column: {names[0]}")


def _parse_votes(value: str) -> int:
    try:
        amount = Decimal(value.replace(",", "").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"Invalid candidate vote count: {value!r}") from exc
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError(
            f"Candidate vote count must be a non-negative integer: {value!r}"
        )
    return int(amount)


def _district(row: dict[str, str]) -> str:
    normalized = {
        key.strip().lower().replace(" ", "_"): value
        for key, value in row.items()
        if key
    }
    value = normalized.get("district", normalized.get("congressional_district", ""))
    value = value.strip()
    return value[:-2] if value.endswith(".0") else value


def process_election_csv(source: str | Path | TextIO) -> list[CandidateVoteData]:
    """Parse candidate rows and sum votes by state, year, race, and party.

    ``source`` may be a path or an already-open text stream. Unsupported
    offices are ignored so broad MEDSL files can be passed directly.
    """
    if hasattr(source, "read"):
        rows = csv.DictReader(source)
        return _aggregate_rows(rows)
    with Path(source).open(encoding="utf-8-sig", newline="") as csv_file:
        return _aggregate_rows(csv.DictReader(csv_file))


def _aggregate_rows(rows: csv.DictReader) -> list[CandidateVoteData]:
    totals: defaultdict[tuple[str, int, ElectionOffice, str, VoteParty], int] = (
        defaultdict(int)
    )
    for row in rows:
        office = _normalize_office(_row_value(row, "office"))
        if office is None:
            continue
        state_fips = normalize_state_fips(
            _row_value(row, "state_fips", "state", "state_abbreviation")
        )
        year = int(_row_value(row, "year"))
        party = normalize_party(_row_value(row, "party"))
        district = _district(row)
        votes = _parse_votes(
            _row_value(row, "candidatevotes", "candidate_votes", "votes")
        )
        totals[(state_fips, year, office, district, party)] += votes

    return [
        CandidateVoteData(
            state_fips=state_fips,
            year=year,
            office=office,
            district=district,
            party=party,
            candidate_votes=candidate_votes,
        )
        for (state_fips, year, office, district, party), candidate_votes in sorted(
            totals.items(), key=lambda item: tuple(str(part) for part in item[0])
        )
    ]
