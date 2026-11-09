# Contributing

Changes should preserve the project's data contracts, security practices, and analytical neutrality. See [the README](README.md) for setup and [data contracts](docs/data-contracts.md) for the current transformation behavior.

## Development setup

Use Python 3.14 or newer and manage dependencies with `uv`:

```bash
uv sync
uv run pytest
```

Set up `.env` from `.env.example` only when exercising code that loads runtime settings or makes external API/database connections. Tests should not need real credentials or a live database.

## Test-first workflow

For each behavior change, add or update a focused test before implementation (Red → Green → Refactor). Use synthetic fixtures for transformations, aggregation, joins, and database behavior. Mock only external boundaries such as HTTP requests; do not mock the internal computations being tested.

Pay particular attention to:

- Exact party-level vote aggregation against input totals.
- Two-character state FIPS normalization, including leading zeroes.
- `(state_fips, year)` join semantics and duplicate dimension keys.
- `NULL` party registration counts for states that do not collect party affiliation, distinct from a collected count of zero.
- SQL persistence and CSV/Parquet exports without non-allowlisted columns.
- Configuration errors that do not expose credential values.

Run the relevant checks before submitting changes:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

If formatting is needed, run `uv run ruff format .` and rerun the checks. Tests use SQLite for persistence checks; a passing test suite is not evidence that a live PostgreSQL deployment or external source download has been validated.

## Change expectations

- Keep secrets, local credentials, downloaded data, and generated exports out of version control. Never add real API keys or personal data to fixtures.
- Preserve neutral, deterministic party normalization. Document intentional changes to category mappings because they can alter historical comparisons.
- Keep input and output schemas explicit. Treat missingness, source coverage, and reference-year semantics as analytical behavior, not incidental implementation details.
- Update the README or data-contract documentation when user-visible behavior, input requirements, output fields, or supported workflows change.
- Do not claim source data have been downloaded, verified, or reconciled unless the change actually performs and tests that work.

## Current workflow boundary

The ingestion modules expose Python functions; there are no supported `python -m ingest.*` or `python -m pipeline` commands at this time. The election and registration source acquisition/parsing stages must be provided by the caller. Avoid documenting a new CLI command unless one is implemented and tested.
