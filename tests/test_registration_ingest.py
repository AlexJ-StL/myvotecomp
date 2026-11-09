from ingest.voter_reg import normalize_registration_records


def test_partisan_registration_counts_are_parsed_and_standardized() -> None:
    records = normalize_registration_records(
        [
            {
                "state": "Alabama",
                "year": "2024",
                "registered_voters": "1,000,000",
                "party_registration_collected": "yes",
                "republican_registrants": "400,000",
                "democrat_registrants": "350,000",
                "other_registrants": "250,000",
            }
        ]
    )

    record = records[0]
    assert record.state_fips == "01"
    assert record.year == 2024
    assert record.registered_voters == 1_000_000
    assert record.republican_registrants == 400_000
    assert record.democrat_registrants == 350_000
    assert record.other_registrants == 250_000
    assert (
        record.republican_registrants
        + record.democrat_registrants
        + record.other_registrants
        == record.registered_voters
    )


def test_open_registration_keeps_uncollected_party_counts_null() -> None:
    records = normalize_registration_records(
        [
            {
                "state_fips": "28",
                "year": 2024,
                "registered_voters": 500_000,
                "party_registration_collected": "no",
                "republican_registrants": 0,
                "democrat_registrants": 0,
                "other_registrants": 0,
            }
        ]
    )

    record = records[0]
    assert record.state_fips == "28"
    assert record.registered_voters == 500_000
    assert record.republican_registrants is None
    assert record.democrat_registrants is None
    assert record.other_registrants is None


def test_missing_party_breakdown_is_not_coerced_to_zero() -> None:
    record = normalize_registration_records(
        [{"state": "Alabama", "year": 2024, "registered_voters": 12}]
    )[0]

    assert record.republican_registrants is None
    assert record.democrat_registrants is None
    assert record.other_registrants is None
