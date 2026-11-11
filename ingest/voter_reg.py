"""Normalization for state voter-registration survey records."""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from ingest.geography import normalize_state_fips
from models import VoterRegistrationRecordData


def _normalized_row(row: Mapping[str, object]) -> dict[str, object]:
    return {str(key).strip().lower().replace(" ", "_").replace("-", "_"): value for key, value in row.items()}


def _first_value(row: Mapping[str, object], *names: str) -> object | None:
    for name in names:
        if name in row:
            return row[name]
    return None


def _parse_count(value: object | None, label: str, required: bool = False) -> int | None:
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
                _first_value(row, "democrat_registrants", "democrat", "dem", "democratic"),
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


def parse_eavs_csv(
    file_path: str,
    year: int,
    state_col: str = "State",
    total_reg_col: str = "A1a",
    dem_col: str | None = "A1b",
    rep_col: str | None = "A1c",
    ind_col: str | None = "A1d",
) -> pd.DataFrame:
    """Parse raw EAC EAVS or state voter registration CSV files into normalized records.

    EAVS (Election Administration and Voting Survey) survey variables typically map to:
    - A1a: Total registered voters (active)
    - A1b: Total registered Democrats (if collected)
    - A1c: Total registered Republicans (if collected)
    - A1d: Total registered Independents / Unaffiliated / Third Party (if collected)

    States operating open registration (without party affiliation) will leave party
    breakdown columns empty or missing, which are parsed cleanly as NULL.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"EAVS file not found at: {file_path}")

    # Read CSV, treating standard missing markers as NaNs
    raw_df = pd.read_csv(path, dtype=str, keep_default_na=True)

    # Required column validation
    if state_col not in raw_df.columns:
        raise KeyError(f"Required state column '{state_col}' not found in CSV headers.")
    if total_reg_col not in raw_df.columns:
        raise KeyError(f"Required total registration column '{total_reg_col}' not found in CSV headers.")

    normalized_records: list[dict[str, object]] = []

    # Group by state to aggregate jurisdiction/county level EAVS rows up to state level
    grouped = raw_df.groupby(state_col)

    for state_val, group in grouped:
        try:
            fips = normalize_state_fips(str(state_val))
        except ValueError:
            # Skip rows with unknown state identifiers.
            continue

        # Convert numeric columns safely, treating uncollected or invalid values as NaN
        total_reg = pd.to_numeric(group[total_reg_col], errors="coerce").sum(min_count=1)

        # If total registration is missing or invalid, skip the state entry
        if pd.isna(total_reg):
            continue

        dem_reg = pd.to_numeric(group[dem_col], errors="coerce").sum(min_count=1) if dem_col in group.columns else None
        rep_reg = pd.to_numeric(group[rep_col], errors="coerce").sum(min_count=1) if rep_col in group.columns else None
        ind_reg = pd.to_numeric(group[ind_col], errors="coerce").sum(min_count=1) if ind_col in group.columns else None

        record_dict = {
            "state_fips": fips,
            "year": year,
            "registered_voters": _parse_count(total_reg, "registered_voters", required=True),
            "democrat_registrants": (_parse_count(dem_reg, "democrat_registrants") if pd.notna(dem_reg) else None),
            "republican_registrants": (_parse_count(rep_reg, "republican_registrants") if pd.notna(rep_reg) else None),
            "other_registrants": (_parse_count(ind_reg, "other_registrants") if pd.notna(ind_reg) else None),
        }

        validated_record = normalize_registration_records([record_dict])[0]
        normalized_records.append(validated_record.model_dump())

    return pd.DataFrame(normalized_records)


def main() -> None:
    """CLI entry point for normalizing voter registration JSON or EAVS CSV inputs."""
    parser = argparse.ArgumentParser(
        description="Normalize voter registration records from EAVS CSV or raw JSON inputs."
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="Path to a JSON file or EAVS CSV file containing registration records.",
    )
    parser.add_argument(
        "--year",
        "-y",
        type=int,
        default=2024,
        help="Election year for EAVS CSV parsing (default: 2024).",
    )
    parser.add_argument(
        "--eavs",
        action="store_true",
        help="Parse input file using the EAVS CSV format parser instead of JSON array.",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File '{file_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"Processing registration data from: {file_path}...")

    if args.eavs or file_path.suffix.lower() == ".csv":
        records = parse_eavs_csv(str(file_path), year=args.year)
        print(f"Successfully normalized {len(records)} voter registration state records.")
        print("\nSample Output:")
        print(records.head())
    else:
        with file_path.open(encoding="utf-8") as file:
            raw_records = json.load(file)
        if not isinstance(raw_records, list) or any(not isinstance(record, dict) for record in raw_records):
            parser.error("JSON input must be an array of registration objects.")

        normalized_records = normalize_registration_records(raw_records)
        print(f"Successfully normalized {len(normalized_records)} registration records.")
        print("\nSample Output:")
        for record in normalized_records[:5]:
            print(record.model_dump())


if __name__ == "__main__":
    main()
