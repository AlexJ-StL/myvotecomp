# AGENT.md

Data pipeline for ingestion, normalization, cross-table joining, and export of U.S. election candidate vote counts (House, Senate, Governor), state demographics (Census ACS population & working-age), and state voter registration metrics (EAC EAVS).

## Analytical Integrity & Engineering Philosophy

1. **Zero-Trust Security Hygiene & Privacy Preservation**
   - Never hardcode secrets, API keys, database credentials, local file paths, hostnames, or personal identifying information (PII).
   - Configuration is strictly loaded at runtime via environment variables using `pydantic-settings`.
   - `.env` files, credentials, local databases, and build artifacts must remain excluded via `.gitignore`.
   - Provide non-sensitive placeholders in `.env.example`.

2. **Data Neutrality & Uncompromising Standardization**
   - Candidate party affiliations must be deterministically mapped and standardized (e.g., `GOP`/`REP` $\to$ `REPUBLICAN`) across disparate sources.
   - States with open registration (where party affiliation is uncollected) must preserve party breakdown totals as explicit `NULL` values rather than defaulting to `0`.
   - Cross-table merges on `(state_fips, year)` must maintain exact mathematical parity across vote totals, demographic age brackets, and registration records.

3. **Strict Test-Driven Development (TDD) & Non-Performative Testing**
   - Write failing unit/integration tests **before** writing implementation code (Red $\to$ Green $\to$ Refactor).
   - High test coverage is an authentic byproduct of thorough verification, never a metric achieved through superficial assertions (e.g., `assert result is not None` is strictly prohibited).
   - Internal data transformations, joins, and aggregates must be executed against real computations using synthetic fixtures.
   - Mocking is strictly isolated to external network calls (e.g., U.S. Census API HTTP endpoints or remote CSV file downloads).

---

## Setup & Environment

Dependencies and virtual environments are managed exclusively with **UV**:

```bash
# Sync dependencies and activate environment
uv sync
source .venv/bin/activate  # Or `uv run <command>`
```

Dependencies are declared in `pyproject.toml` (`pandas`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `psycopg2-binary`, `httpx`, `openai`). Dev tools include `pytest`, `pytest-mock`, and `ruff`.

---

## Commands & CLI Options

| Command | Arguments / Flags | What it does |
| :-- | :-- | :-- |
| `uv run python -m ingest.elections` | `--file` / `-f` (path, required) | Ingests and normalizes raw election CSV data (House, Senate, Governor), aggregating party totals. |
| `uv run python -m ingest.census` | `--year` / `-y` (int, default: 2024) | Fetches state total and working-age population statistics from the Census ACS 5-Year API using `CENSUS_API_KEY`. |
| `uv run python -m ingest.voter_reg` | `--file` / `-f` (path, required) | Parses and normalizes a JSON file of state-level voter registration counts & party breakdowns. |
| `uv run python -m pipeline` | — | Executes full pipeline driver: ingest, join on (`state_fips`, `year`), load to PostgreSQL, and export CSV/Parquet. |
| `uv run ruff check .` | — | Lint verification using Ruff. |
| `uv run ruff format --check .` | — | Formatting check. |
| `uv run ruff check --fix .` | — | Apply automatic lint fixes — run before committing. |
| `uv run pytest` | — | Run the complete TDD test suite. |
| `uv run pytest --cov=src` | — | Run test suite with line and branch coverage report. |

---

## Module CLI Details

1. Election Ingestion (`ingest.elections`):

- Flags: `--file` or `-f` (Path to election CSV).
- Example: `uv run python -m ingest.elections --file data/raw/elections.csv`

1. Census Ingestion (`ingest.census`):

- Flags: `--year` or `-y` (Survey year integer, defaults to 2024).
- Requirements: Valid `CENSUS_API_KEY` present in `.env` / environment.
- Example: `uv run python -m ingest.census --year 2024`

1. Voter Registration Ingestion (`ingest.voter_reg`):

- Flags: `--file` or `-f` (Path to voter registration JSON file).
- Example: `uv run python -m ingest.voter_reg --file data/raw/voter_registration.json`

---

## Architecture

| Module / Directory | Role |
| :-- | :-- |
| `config.py` | Central `pydantic-settings` configuration loader; exports OpenRouter `openai.OpenAI` client builder and DB connection settings. |
| `models.py` | Pydantic and SQLAlchemy schemas for `CandidateVote`, `DemographicRecord`, and `VoterRegistrationRecord`. |
| `ingest/elections.py` | Ingests MEDSL / FEC raw CSV data, cleans party labels, aggregates candidate vote counts by race/party, and provides a standalone CLI parser. |
| `ingest/census.py` | Queries U.S. Census ACS API for total population (`B01001_001E`) and working-age populations (18–64 / 18+), providing a standalone CLI parser. |
| `ingest/voter_reg.py` | Parses state-level voter registration statistics, maps party-affiliated vs. open-registration states, and provides a standalone CLI parser. |
| `pipeline.py` | Single entry point for dataset joining on (`state_fips`, `year`), PostgreSQL persistence, and sanitized file export. |
| `tests/` | Comprehensive test suite mirroring module structure under TDD principles. |

---

## Code & LLM Conventions

1. OpenRouter / LLM Inference Rule

- No Native Vendor SDKs: Do not use `anthropic` or `google-generativeai` libraries directly.
- Use the `openai` SDK configured for OpenRouter (`base_url="https://openrouter.ai/api/v1"`).
- Load `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` dynamically from `config.py`.

1. Database Hygiene

- PostgreSQL is the primary store. Connections use SQLAlchemy engine bindings constructed from `pydantic-settings`.
- Never write raw unparameterized SQL strings; use SQLAlchemy ORM/Core bindings.

1. Code Style

- Strict adherence to Ruff formatting defaults.
- Explicit Pydantic type annotations across all data flow boundaries.

---

## Testing Philosophy & Defect Prevention

Every feature or bug fix must start with a failing test case in `tests/`.

Mandatory Assertions

- Mathematical Parity: Test that candidate vote aggregates by party match raw totals.
- Null Safety: Verify open-registration states persist `NULL` values for party counts instead of `0`.
- FIPS Validation: Validate that all state entries are normalized to valid 2-character FIPS strings (e.g., `"01"`, `"28"`).
- Security Check: Verify that loading `config.py` without required environment variables fails explicitly without exposing credential fragments in error traces.
