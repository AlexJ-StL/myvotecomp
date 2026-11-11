# Data contracts and methodology

This document describes the record shapes and transformations currently implemented in `myVoteComp`. It is not a source-specific guide to downloading MEDSL, FEC, or EAC data: acquisition and source-file parsing for election and registration records remain the caller's responsibility.

## Common key

All normalized records carry:

| Field | Type / rule | Meaning |
| --- | --- | --- |
| `state_fips` | String of exactly two digits | Census state or territory FIPS code; leading zeroes are preserved. The normalizer accepts recognized state or territory FIPS values, USPS abbreviations, and names. Numeric codes are zero-padded; unknown or unsupported codes raise an error. |
| `year` | Non-negative integer | Year associated with the source record. Use the source's documented reference year; the pipeline does not convert between election, survey, or ACS reference years. |

Every join uses both key fields: `(state_fips, year)`. Matching on state alone is deliberately not used.

## Normalized records and persisted tables

### Candidate votes — `candidate_votes`

`process_election_csv()` reads candidate-level CSV rows and aggregates them into one record per state, year, office, district, and party.

| Field | Meaning |
| --- | --- |
| `office` | One of `HOUSE`, `SENATE`, or `GOVERNOR`. Other offices are ignored. |
| `district` | Source district string when present; otherwise an empty string. |
| `party` | One of `REPUBLICAN`, `DEMOCRAT`, or `INDEPENDENT_OTHER`. |
| `candidate_votes` | Sum of non-negative integer candidate vote counts for that party/race key. |

The database enforces uniqueness on `(state_fips, year, office, district, party)`. Candidate names and original party labels are not stored, and aggregation does not retain individual candidate rows. Recognized Republican aliases include `R`, `REP`, `REPUBLICAN`, and `GOP`; recognized Democratic aliases include `D`, `DEM`, `DEMOCRAT`, `DEMOCRATIC`, and `DFL`. All other labels map to `INDEPENDENT_OTHER`, so inspect source labels before interpreting that category as a substantive political grouping.

The election CSV parser expects columns corresponding to:

- `office`
- `year`
- `party`
- `candidatevotes`, `candidate_votes`, or `votes`
- `state_fips`, `state`, or `state_abbreviation`
- Optional `district` or `congressional_district`

Column headers are case-insensitive and spaces are normalized to underscores. Vote counts must be finite, non-negative integers. Rows for unsupported offices are skipped; missing or malformed required fields raise an error.

### Demographics — `demographic_records`

`fetch_census_demographics(year, api_key, client=None)` requests state-level ACS 5-year data from the Census API. It retrieves total population (`B01001_001E`) and age/sex counts from table B01001, then computes:

| Field | Meaning |
| --- | --- |
| `total_population` | ACS total population estimate from `B01001_001E`. |
| `working_age_18_64` | Sum of B01001 age bins for ages 18 through 64, across male and female columns. |
| `population_18_plus` | Sum of B01001 age bins for ages 18 and older, across male and female columns. |

The Pydantic contract checks `working_age_18_64 <= population_18_plus <= total_population`. The database enforces one demographic record per state and year. ACS values are estimates; retain the ACS vintage and source information with downstream analysis.

### Voter registration — `voter_registration_records`

`normalize_registration_records()` accepts an iterable of mappings and returns validated state/year registration records. `parse_eavs_csv(file_path, year, ...)` reads an EAVS-style CSV, aggregates jurisdiction rows by state, and returns a DataFrame of those normalized records. Its default columns are `State`, `A1a` (total), `A1b` (Democratic), `A1c` (Republican), and `A1d` (other); optional column arguments support files with different headers. Missing party counts remain null, invalid state identifiers and groups without a usable total are skipped, and aggregated counts are validated as non-negative integers. Neither function downloads source files or independently determines the authoritative source year.

| Field | Meaning |
| --- | --- |
| `registered_voters` | Required non-negative integer total registration count. |
| `republican_registrants` | Republican registration count, or null when not collected/unavailable. |
| `democrat_registrants` | Democratic registration count, or null when not collected/unavailable. |
| `other_registrants` | Other/independent/unaffiliated registration count, or null when not collected/unavailable. |

Accepted aliases include common state/name variants: `total_registered` and `total_registrations` for the total; `rep`/`gop`, `dem`/`democratic`, and `other`/`independent`/`unaffiliated` for party counts. An explicit `party_registration_collected` value or open/nonpartisan `registration_type` signals that partisan registration is not collected. In that case, all three party counts become null even if the source encoded them as zero. For states that collect partisan registration, an actual zero remains zero. Missing optional party counts otherwise remain null; the normalizer does not infer them by subtraction.

The database enforces one registration record per state and year.

## Join, persistence, and exports

`join_datasets(votes, demographics, registrations)` starts from the vote records and left-joins demographics and registration records on `(state_fips, year)`. This preserves vote rows without matching dimensions, with missing joined fields represented as null. Each dimension must be many-to-one relative to vote rows; duplicate state/year dimension keys raise an error instead of multiplying results.

`persist_records()` inserts the three normalized input collections together in a transaction. The pipeline does not upsert or deduplicate against existing database rows; the uniqueness constraints reject duplicate keys already persisted. Schema creation in examples uses SQLAlchemy metadata only as a local bootstrap. There is no migration tool or managed schema lifecycle in the repository.

`export_dataset()` accepts `.csv` and `.parquet` destinations and emits an allowlisted set of analytical columns. It does not export arbitrary extra DataFrame columns. The export function does not inspect or remove PII embedded in an allowed field; input quality and safe handling remain the caller's responsibility.

## Interpretation and limitations

1. **Different measures are not interchangeable.** Candidate votes, registered voters, and ACS population estimates are not expected to sum to the same number. The pipeline joins values; it does not assert cross-source mathematical parity or validate source coverage.
2. **Null is meaningful.** Do not convert uncollected party registration to zero unless a specific analytical method justifies that change.
3. **Source years require care.** The join key is a year integer, not a measurement-period harmonizer. Confirm that the source year's semantics align before joining.
4. **Aggregation loses detail.** Candidate names and original labels are discarded when vote rows are grouped by party. Keep source files or an immutable raw layer when candidate-level analysis or auditability is needed.
5. **Coverage is not completed by the join.** A missing demographic or registration row does not cause a vote row to be dropped. Review nulls and compare source geography/year coverage before publishing results.
6. **No provenance registry is built in.** Track source URLs, release identifiers, retrieval dates, licenses, and transformation versions outside the output or in a future metadata layer.
