"""Census ACS requests and state demographic calculations."""

import argparse
import sys

import httpx

from config import get_settings
from ingest.geography import normalize_state_fips
from models import DemographicRecordData

_BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"
_AGE_VARIABLES = tuple(f"B01001_{number:03d}E" for number in (*range(7, 26), *range(31, 50)))
_WORKING_AGE_VARIABLES = tuple(f"B01001_{number:03d}E" for number in (*range(7, 20), *range(31, 44)))
_ADULT_AGE_VARIABLES = _AGE_VARIABLES
_CENSUS_VARIABLES = ("NAME", "B01001_001E", *_AGE_VARIABLES, "state")


def fetch_census_demographics(
    year: int,
    api_key: str,
    client: httpx.Client | None = None,
) -> list[DemographicRecordData]:
    """Fetch ACS 5-year state counts and derive 18-64 and 18+ populations."""
    if client is None:
        with httpx.Client(timeout=30.0) as owned_client:
            return _fetch_with_client(year, api_key, owned_client)
    return _fetch_with_client(year, api_key, client)


def _fetch_with_client(
    year: int,
    api_key: str,
    client: httpx.Client,
) -> list[DemographicRecordData]:
    response = client.get(
        _BASE_URL.format(year=year),
        params={
            "get": ",".join(_CENSUS_VARIABLES),
            "for": "state:*",
            "key": api_key,
        },
    )
    if response.is_error:
        raise RuntimeError(f"Census API request failed with status {response.status_code}")
    payload = response.json()
    if not isinstance(payload, list) or len(payload) < 1:
        raise ValueError("Census API returned an invalid tabular response")
    header = payload[0]
    if not isinstance(header, list):
        raise ValueError("Census API response is missing its header row")
    positions = {str(name): index for index, name in enumerate(header)}
    required = {"B01001_001E", "state", *_AGE_VARIABLES}
    missing = required - positions.keys()
    if missing:
        raise ValueError(f"Census API response is missing variables: {', '.join(sorted(missing))}")

    records: list[DemographicRecordData] = []
    for row in payload[1:]:
        if not isinstance(row, list) or len(row) != len(header):
            raise ValueError("Census API response contains a malformed data row")
        values = {name: _parse_count(row[positions[name]], name) for name in required - {"state"}}
        records.append(
            DemographicRecordData(
                state_fips=normalize_state_fips(row[positions["state"]]),
                year=year,
                total_population=values["B01001_001E"],
                working_age_18_64=sum(values[name] for name in _WORKING_AGE_VARIABLES),
                population_18_plus=sum(values[name] for name in _ADULT_AGE_VARIABLES),
            )
        )
    return records


def _parse_count(value: object, variable: str) -> int:
    try:
        count = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Census variable {variable} is not an integer") from exc
    if count < 0:
        raise ValueError(f"Census variable {variable} is negative")
    return count


def main() -> None:
    """CLI entry point for fetching Census ACS demographic data."""
    parser = argparse.ArgumentParser(
        description="Fetch state total and working-age population from Census ACS 5-Year API."
    )
    parser.add_argument(
        "--year",
        "-y",
        type=int,
        default=2024,
        help="Census ACS survey year to query (default: 2024).",
    )
    args = parser.parse_args()

    try:
        settings = get_settings()
        api_key = settings.CENSUS_API_KEY.get_secret_value()
    except Exception as e:
        print(
            f"Error loading CENSUS_API_KEY from environment/settings: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Fetching Census ACS demographics for year {args.year}...")
    records = fetch_census_demographics(year=args.year, api_key=api_key)
    print(f"Successfully retrieved demographic records for {len(records)} states.")
    print("\nSample Output:")
    print(records[:5])


if __name__ == "__main__":
    main()
