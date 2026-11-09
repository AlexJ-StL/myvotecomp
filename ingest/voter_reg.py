"""Normalization for state voter-registration survey records."""

from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation

from ingest.geography import normalize_state_fips
from models import VoterRegistrationRecordData


def _normalized_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        str(key).strip().lower().replace(" ", "_").replace("-", "_"): value
        for key, value in row.items()
    }


def _first_value(row: Mapping[str, object], *names: str) -> object | None:
    for name in names:
        if name in row:
            return row[name]
    return None


def _parse_count(
    value: object | None, label: str, required: bool = False
) -> int | None:
    if value is None or not str(value).strip():
        if required:
            raise ValueError(f"Registration data is missing {label}")
        return None
    try:
        count = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"Registration field {label} is not numeric") from exc
    if not count.is_finite() or count < 0 or count != count.to_integral_value():
        raise ValueError(f"Registration field {label} must be a non-negative integer")
    return int(count)


def _party_data_collected(row: Mapping[str, object]) -> bool | None:
    collected = _first_value(row, "party_registration_collected")
    if collected is not None:
        if isinstance(collected, bool):
            return collected
        label = str(collected).strip().lower()
        if label in {"yes", "y", "true", "1", "collected", "partisan"}:
            return True
        if label in {
            "no",
            "n",
            "false",
            "0",
            "open",
            "nonpartisan",
            "not_collected",
        }:
            return False
        raise ValueError("party_registration_collected must be a recognizable boolean")

    registration_type = str(_first_value(row, "registration_type") or "")
    if registration_type.strip().lower() in {"open", "nonpartisan", "non-partisan"}:
        return False
    return None


def normalize_registration_records(
    records: Iterable[Mapping[str, object]],
) -> list[VoterRegistrationRecordData]:
    """Convert EAVS-like rows to validated, FIPS-keyed registration records.

    An explicit open/nonpartisan state always receives null party counts,
    including when source files encode those uncollected values as zero.
    """
    normalized: list[VoterRegistrationRecordData] = []
    for record in records:
        row = _normalized_row(record)
        collected = _party_data_collected(row)
        state = _first_value(row, "state_fips", "state", "state_abbreviation")
        year = _first_value(row, "year", "election_year")
        total = _first_value(
            row,
            "registered_voters",
            "total_registered",
            "total_registrations",
        )
        party_counts = {
            "republican_registrants": _parse_count(
                _first_value(row, "republican_registrants", "republican", "rep", "gop"),
                "republican_registrants",
            ),
            "democrat_registrants": _parse_count(
                _first_value(
                    row, "democrat_registrants", "democrat", "dem", "democratic"
                ),
                "democrat_registrants",
            ),
            "other_registrants": _parse_count(
                _first_value(
                    row,
                    "other_registrants",
                    "independent_other_registrants",
                    "other",
                    "independent",
                    "unaffiliated",
                ),
                "other_registrants",
            ),
        }
        if collected is False:
            party_counts = {name: None for name in party_counts}
        total_count = _parse_count(total, "registered_voters", required=True)
        if total_count is None:
            raise ValueError("Registration data is missing registered_voters")

        normalized.append(
            VoterRegistrationRecordData(
                state_fips=normalize_state_fips(state),
                year=int(str(year)),
                registered_voters=total_count,
                **party_counts,
            )
        )
    return normalized
