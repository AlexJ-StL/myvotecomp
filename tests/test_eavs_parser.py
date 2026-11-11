import pytest

from ingest.voter_reg import main, parse_eavs_csv


def test_parse_eavs_csv_aggregates_jurisdictions_by_state(tmp_path) -> None:
    csv_path = tmp_path / "eavs.csv"
    csv_path.write_text(
        "State,A1a,A1b,A1c,A1d\nAlabama,100,30,40,30\nAlabama,50,20,10,20\n",
        encoding="utf-8",
    )

    records = parse_eavs_csv(str(csv_path), year=2024)

    assert len(records) == 1
    record = records.iloc[0]
    assert record["state_fips"] == "01"
    assert record["year"] == 2024
    assert record["registered_voters"] == 150
    assert record["democrat_registrants"] == 50
    assert record["republican_registrants"] == 50
    assert record["other_registrants"] == 50


def test_parse_eavs_csv_preserves_missing_open_registration_party_counts(tmp_path) -> None:
    csv_path = tmp_path / "open-registration.csv"
    csv_path.write_text("State,A1a,A1b,A1c,A1d\nMississippi,200,,,\n", encoding="utf-8")

    record = parse_eavs_csv(str(csv_path), year=2024).iloc[0]

    assert record["registered_voters"] == 200
    assert record["democrat_registrants"] is None
    assert record["republican_registrants"] is None
    assert record["other_registrants"] is None


@pytest.mark.parametrize(
    ("state", "expected_fips"),
    [("AL", "01"), ("Mississippi", "28")],
)
def test_parse_eavs_csv_normalizes_state_names_and_abbreviations(
    tmp_path,
    state: str,
    expected_fips: str,
) -> None:
    csv_path = tmp_path / "state.csv"
    csv_path.write_text(f"State,A1a\n{state},25\n", encoding="utf-8")

    record = parse_eavs_csv(str(csv_path), year=2024).iloc[0]

    assert record["state_fips"] == expected_fips
    assert len(record["state_fips"]) == 2
    assert record["state_fips"].isdigit()


@pytest.mark.parametrize(
    ("headers", "row", "missing_header"),
    [("A1a", "100", "State"), ("State", "Alabama", "A1a")],
)
def test_parse_eavs_csv_requires_state_and_total_headers(
    tmp_path,
    headers: str,
    row: str,
    missing_header: str,
) -> None:
    csv_path = tmp_path / "missing-header.csv"
    csv_path.write_text(f"{headers}\n{row}\n", encoding="utf-8")

    with pytest.raises(KeyError, match=missing_header):
        parse_eavs_csv(str(csv_path), year=2024)


def test_registration_cli_forces_eavs_parsing_and_uses_year(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    csv_path = tmp_path / "registration.data"
    csv_path.write_text("State,A1a\nAlabama,25\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["voter_reg", "--file", str(csv_path), "--eavs", "--year", "2020"],
    )

    main()

    output = capsys.readouterr().out
    assert "Successfully normalized 1 voter registration state records." in output
    assert "2020" in output
