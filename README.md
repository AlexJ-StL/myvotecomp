# myVoteComp

`myVoteComp` is a Python data pipeline for normalizing and comparing U.S. election results with state-level population and voter-registration data. It validates source records, joins them on Census state FIPS and year, persists the normalized inputs to PostgreSQL, and can export an allowlisted analytical dataset as CSV or Parquet.

> **Project status:** the repository currently provides ingestion and pipeline functions, not a turnkey command-line application. Election results and registration records must be supplied by the caller; only Census ACS data is fetched by a built-in network client. There is no automatic MEDSL, FEC, or EAC download, database migration system, or production deployment configuration yet.

## What it does

- Aggregates House, Senate, and Governor candidate votes by state, year, office, district, and normalized party.
- Fetches state population counts from the Census American Community Survey (ACS) 5-year API and derives population age 18–64 and age 18+.
- Normalizes externally supplied voter-registration rows while preserving uncollected party breakdowns as `NULL`.
- Joins the records on the complete `(state_fips, year)` key. Vote rows are retained as the left-hand side; each demographic and registration input must have at most one row per state and year.
- Persists the three normalized input tables in one transaction and optionally exports the joined analytical data to `.csv` or `.parquet`.

The pipeline does **not** assert that vote totals, registration counts, and population estimates reconcile with one another. These are separate measures from different sources and may have different definitions, coverage, or reference periods.

## Requirements

- Python 3.14 or newer (as declared in `pyproject.toml`).
- [uv](https://docs.astral.sh/uv/) for dependency and virtual-environment management.
- PostgreSQL for normal persistence. Unit tests use SQLite and do not require a running PostgreSQL server.
- A Census API key for Census requests. The current settings model also requires OpenRouter configuration even when no LLM functionality is used.

## Set up

```bash
uv sync
Copy-Item .env.example .env  # PowerShell; edit .env with your local values
```

On macOS or Linux, copy the template with `cp .env.example .env`. Set real credentials only in `.env` or in the process environment; do not commit them. The `.env` file is Git-ignored.

| Variable | Purpose |
| --- | --- |
| `POSTGRES_DB` | PostgreSQL database name |
| `POSTGRES_USER` | Database username |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_HOST` | Database host |
| `POSTGRES_PORT` | Database port (1–65535) |
| `CENSUS_API_KEY` | Census API key used by the ACS request |
| `OPENROUTER_API_KEY` | OpenRouter key used only when constructing the optional OpenRouter client |
| `OPENROUTER_MODEL` | OpenRouter model identifier; required by settings, but not otherwise used by the data pipeline |

All listed settings are required by `get_settings()` today. Database connection URLs are assembled with SQLAlchemy's URL builder so reserved characters in passwords are handled safely.

## Run the pipeline from Python

The following illustrates the current function-based workflow. Supply a local election CSV and voter-registration records prepared from sources you have obtained and checked. The example's registration mapping is synthetic; replace it with your own parsed data.

```python
from config import get_settings
from ingest.census import fetch_census_demographics
from ingest.elections import process_election_csv
from ingest.voter_reg import normalize_registration_records
from models import Base
from pipeline import build_engine, run_pipeline

settings = get_settings()
engine = build_engine(settings)

# Bootstrap tables for a new local database. Use a migration process before
# managing schema changes in a shared or production database.
Base.metadata.create_all(engine)

votes = process_election_csv("data/raw/elections.csv")
demographics = fetch_census_demographics(
    year=2024,
    api_key=settings.CENSUS_API_KEY.get_secret_value(),
)
registrations = normalize_registration_records(
    [
        {
            "state": "AL",
            "year": 2024,
            "registered_voters": 1000,
            "registration_type": "open",
        }
    ]
)

joined = run_pipeline(
    votes,
    demographics,
    registrations,
    engine=engine,
    export_paths=["data/processed/election-comparison.csv"],
)
print(joined.head())
```

`process_election_csv()` accepts a path or open text stream. It expects a CSV with fields corresponding to `office`, `year`, `party`, vote count (`candidatevotes`, `candidate_votes`, or `votes`), and geography (`state_fips`, `state`, or `state_abbreviation`). `district` is optional. Unsupported offices are skipped. Registration normalization accepts an iterable of mappings; `parse_eavs_csv()` also aggregates standard EAVS CSV rows by state. The repository does not download election or registration source files.

For individual function signatures and source-field details, see [Data contracts and methodology](docs/data-contracts.md).

### Run an individual ingestion CLI

Each ingestion module can also be run directly. These commands normalize or fetch the indicated input and print a short sample; they do not persist records or run the complete join/export pipeline.

```bash
uv run python -m ingest.elections --file data/raw/elections.csv
uv run python -m ingest.census --year 2024
uv run python -m ingest.voter_reg --file data/raw/voter_registration.json
```

The election command reads a local CSV, the registration command reads a JSON array or EAVS CSV (CSV is detected by the `.csv` extension; `--eavs` can force EAVS parsing), and the Census command fetches ACS data using `CENSUS_API_KEY`. EAVS parsing defaults to `State`, `A1a`, `A1b`, `A1c`, and `A1d` columns; `--year` defaults to 2024. There is no `python -m pipeline` end-to-end CLI; use the Python workflow above to join, persist, and export records.

## Data and analytical rules

- Geographic keys are normalized to two-character Census FIPS strings (for example, Alabama is `"01"`). Recognized state and territory names, USPS abbreviations, and numeric FIPS values are accepted; numeric values are zero-padded, and unknown or unsupported FIPS codes are rejected.
- Candidate party labels such as `GOP`/`REP` and `DEM`/`DFL` are normalized. Unrecognized labels map to `INDEPENDENT_OTHER`; the source label and candidate identity are not retained in the aggregated vote records.
- ACS population totals come from `B01001_001E`; the age-specific ACS counts are summed to calculate the age 18–64 and age 18+ measures.
- When a state does not collect registration by party, the party counts remain null, not zero. A zero means a collected count of zero; `NULL` means unavailable or uncollected.
- Dimension duplicates for a `(state_fips, year)` key cause the join to fail rather than multiply vote rows.
- CSV/Parquet export selects only the public analytical columns defined by the pipeline. This is an output-schema allowlist, not a general-purpose PII detection or redaction system.

Refer to [Data contracts and methodology](docs/data-contracts.md) for column definitions, accepted input fields, and interpretation notes.

## Development and verification

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests use synthetic records for transformations and SQLite for persistence/export checks. External Census HTTP behavior is tested with a mocked HTTP transport; running the test suite does not download source datasets or require API credentials.

Contribution and test-first conventions are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Project layout

```text
config.py                 Runtime configuration and database/OpenRouter clients
models.py                 Validated Pydantic contracts and SQLAlchemy tables
pipeline.py               State/year joins, persistence, and allowlisted exports
ingest/
  elections.py            Election CSV normalization and party aggregation
  census.py               Census ACS request and population calculations
  voter_reg.py            Voter-registration mapping normalization and EAVS CSV parsing
  geography.py            State name/abbreviation/FIPS normalization
tests/                    Unit and integration-style tests
docs/
  data-contracts.md        Field definitions, input expectations, and caveats
```

## Data sourcing and attribution

This project transforms data; it does not establish the provenance, license, completeness, or accuracy of caller-supplied election and registration files. Record the source organization, dataset and release/version, download date, license/terms, and any preprocessing alongside each input. Review source documentation before comparing measures across states or years. See the Census Bureau's [ACS API documentation](https://www.census.gov/data/developers/data-sets/acs-5year.html) for ACS coverage and definitions.
