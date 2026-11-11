import json
import sys

import pytest

import ingest.voter_reg as voter_reg
from ingest.voter_reg import main, normalize_registration_records


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
        record.republican_registrants + record.democrat_registrants + record.other_registrants
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


def test_cli_prints_sample_records(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "registration.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "state": "Alabama",
                    "year": 2024,
                    "registered_voters": 100,
                    "registration_type": "open",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["voter_reg", "--file", str(input_path)])

    main()

    output = capsys.readouterr().out
    assert "Successfully normalized 1 registration records." in output
    assert "state_fips" in output
    assert "'01'" in output


def test_cli_rejects_json_that_is_not_an_array(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "registration.json"
    input_path.write_text(json.dumps({"state": "Alabama"}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["voter_reg", "--file", str(input_path)])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    assert "JSON input must be an array of registration objects." in capsys.readouterr().err


def test_missing_party_breakdown_is_not_coerced_to_zero() -> None:
    record = normalize_registration_records([{"state": "Alabama", "year": 2024, "registered_voters": 12}])[0]

    assert record.republican_registrants is None
    assert record.democrat_registrants is None
    assert record.other_registrants is None


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("NaN", "non-negative integer"),
        ("-1", "non-negative integer"),
        ("1.5", "non-negative integer"),
        ("not-a-count", "is not numeric"),
    ],
)
def test_registration_counts_reject_invalid_numeric_values(value, message) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_registration_records([{"state": "Alabama", "year": 2024, "registered_voters": value}])


def test_registration_requires_total_and_recognizable_party_collection_status() -> None:
    with pytest.raises(ValueError, match="missing registered_voters"):
        normalize_registration_records([{"state": "Alabama", "year": 2024}])

    with pytest.raises(ValueError, match="recognizable boolean"):
        normalize_registration_records(
            [
                {
                    "state": "Alabama",
                    "year": 2024,
                    "registered_voters": 100,
                    "party_registration_collected": "sometimes",
                }
            ]
        )


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        (True, True),
        ("YES", True),
        ("collected", True),
        (False, False),
        ("N", False),
        ("0", False),
    ],
)
def test_registration_party_collection_flags_are_normalized(flag, expected) -> None:
    record = normalize_registration_records(
        [
            {
                "state": "AL",
                "year": 2024,
                "registered_voters": 20,
                "party_registration_collected": flag,
                "rep": 10,
                "dem": 5,
                "other": 5,
            }
        ]
    )[0]

    if expected:
        assert record.republican_registrants == 10
        assert record.democrat_registrants == 5
        assert record.other_registrants == 5
    else:
        assert record.republican_registrants is None
        assert record.democrat_registrants is None
        assert record.other_registrants is None


def test_registration_aliases_open_registration_type() -> None:
    records = normalize_registration_records(
        [
            {
                "State Abbreviation": "AL",
                "Election-Year": "2024",
                "Total Registrations": "1,200",
                "Registration-Type": "non-partisan",
                "Republican": 0,
                "Democratic": 0,
                "Unaffiliated": 0,
            }
        ]
    )

    assert len(records) == 1
    assert records[0].state_fips == "01"
    assert records[0].registered_voters == 1200
    assert records[0].republican_registrants is None
    assert records[0].democrat_registrants is None
    assert records[0].other_registrants is None


def test_registration_cli_reports_nonexistent_file(monkeypatch, capsys, tmp_path) -> None:
    missing_path = tmp_path / "missing.json"
    monkeypatch.setattr(sys, "argv", ["voter_reg", "--file", str(missing_path)])

    with pytest.raises(SystemExit) as exc_info:
        voter_reg.main()

    assert exc_info.value.code == 1
    assert f"Error: File '{missing_path}' does not exist." in capsys.readouterr().err


def test_registration_cli_rejects_non_object_array_entries(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "registration.json"
    input_path.write_text(json.dumps([{"state": "AL"}, "not-an-object"]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["voter_reg", "--file", str(input_path)])

    with pytest.raises(SystemExit) as exc_info:
        voter_reg.main()

    assert exc_info.value.code == 2
    assert "JSON input must be an array of registration objects." in capsys.readouterr().err
