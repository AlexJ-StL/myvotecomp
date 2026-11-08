# AGENT.md

Data pipeline for ingestion, normalization, cross-table joining, and export of U.S. election candidate vote counts (House, Senate, Governor), state demographics (Census ACS population & working-age), and state voter registration metrics (EAC EAVS).

---

## Analytical Integrity & Engineering Philosophy

1. Zero-Trust Security Hygiene & Privacy Preservation
  - Never hardcode secrets, API keys, database credentials, local file paths, hostnames, or personal identifying information (PII).
  - Configuration is strictly loaded at runtime via environment variables using `pydantic-settings`.
  - `.env` files, credentials, local databases, and build artifacts must remain excluded via `.gitignore`.
  - Provide non-sensitive placeholders in ``.env`.example`.
2. Data Neutrality & Uncompromising Standardization
  - Candidate party affiliations must be deterministically mapped and standardized (e.g., `GOP`/`REP` $\to$ `REPUBLICAN`) across disparate sources.
  - States with open registration (where party affiliation is uncollected) must preserve party breakdown totals as explicit `NULL` values rather than defaulting to 0.
  - Cross-table merges on (`state_fips`, `year`) must maintain exact mathematical parity across vote totals, demographic age brackets, and registration records.
3. Strict Test-Driven Development (TDD) & Non-Performative Testing
  - Write failing unit/integration tests before writing implementation code (Red $\to$ Green $\to$ Refactor).
  - High test coverage is an authentic byproduct of thorough verification, never a metric achieved through superficial assertions (e.g., `assert result is not None` is strictly prohibited).
  - Internal data transformations, joins, and aggregates must be executed against real computations using synthetic fixtures.
  - Mocking is strictly isolated to external network calls (e.g., U.S. Census API HTTP endpoints or remote CSV file downloads).

---

## Setup & Environment

Dependencies and virtual environments are managed exclusively with UV:

```BAsh
# Sync dependencies and activate environment
uv sync
source .venv/bin/activate  # Or `uv run <command>`
```
Dependencies are declared in `pyproject.toml` (`pandas`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `psycopg2-binary`, `httpx`, `openai`). Dev tools include `pytest`, `pytest-mock`, pytest-cov and `ruff`.

---

## Commands

| Command | What it does |
| :-- | :-- |
| `uv run python -m ingest.elections` | Download/parse candidate vote counts for House, Senate, and Governor races |
| `uv run python -m ingest.census` | Ingest Census ACS total & working-age population statistics via Census API |
| `uv run python -m ingest.voter_reg` | Parse EAC EAVS voter registration counts & party breakdowns |
| `uv run python -m pipeline` | Execute full pipeline: ingest, join, load to PostgreSQL, and export sanitized CSV/Parquet |
| `uv run ruff check .` | Lint verification using Ruff |
| `uv run ruff format --check .` | Formatting check |
| `uv run ruff check --fix .` | Apply automatic lint fixes — run before committing |
| `uv run pytest` | `Run the complete TDD test suite |
| `uv run pytest --cov=src` | Run test suite with line and branch coverage report |

---

## Architecture

| Module / Directory | Role |
| :-- | :-- |
| `config.py` | Central pydantic-settings configuration loader; exports OpenRouter openai.OpenAI client builder and DB connection settings. |
| `models.py` | Pydantic and SQLAlchemy schemas for CandidateVote, DemographicRecord, and VoterRegistrationRecord. |
| `ingest/elections.py` | Ingests MEDSL / FEC raw CSV data, cleans party labels, and aggregates candidate vote counts by race/party. |
| `ingest/census.py` | Queries U.S. Census ACS API for total population (B01001_001E) and working-age populations (18–64 / 18+). |
| `ingest/voter_reg.py` | Parses state-level voter registration statistics and maps party-affiliated vs. open-registration states. |
| `pipeline.py` | Single entry point for dataset joining on (state_fips, year), PostgreSQL persistence, and sanitized file export. |
| `tests/` | Comprehensive test suite mirroring module structure under TDD principles. |

---

## Code & LLM Conventions

1. OpenRouter / LLM Inference Rule
- No Native Vendor SDKs: Do not use `anthropic` or `google-generativeai` libraries directly.
- Use the `openai` SDK configured for OpenRouter (`base_url="[https://openrouter.ai/api/v1](https://openrouter.ai/api/v1)"`).
- Load `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` dynamically from `config.py`.

2. Database Hygiene
- PostgreSQL is the primary store. Connections use SQLAlchemy engine bindings constructed from `pydantic-settings`.
- Never write raw unparameterized SQL strings; use SQLAlchemy ORM/Core bindings.

3. Code Style
- Strict adherence to Ruff formatting defaults.
- Explicit Pydantic type annotations across all data flow boundaries.

---

## Testing Philosophy & Defect Prevention

Every feature or bug fix must start with a failing test case in `tests/`.

---

##Mandatory Assertions

- Mathematical Parity: Test that candidate vote aggregates by party match raw totals.
- Null Safety: Verify open-registration states persist `NULL` values for party counts instead of 0.
- FIPS Validation: Validate that all state entries are normalized to valid 2-character FIPS strings (e.g., `"01"`, `"28"`).
- Security Check: Verify that loading `config.py` without required environment variables fails explicitly without exposing credential fragments in error traces.