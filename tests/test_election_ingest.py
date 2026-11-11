import sys
from io import StringIO

import pytest

import ingest.elections as elections
from ingest.elections import normalize_party, process_election_csv
from models import CandidateVoteData, ElectionOffice, VoteParty

ELECTION_CSV = """year,state,office,district,candidate,party,candidatevotes
2020,AL,US HOUSE,1,Example Republican,GOP,100
2020,AL,US HOUSE,1,Another Republican,REP,25
2020,AL,US HOUSE,1,Example Democrat,DEM,200
2020,AL,US HOUSE,1,Example Independent,IND,20
2020,AL,US HOUSE,1,Example Green,GRN,5
2022,Mississippi,GOVERNOR,,Example Republican,GOP,310
2022,Mississippi,GOVERNOR,,Another Republican,REP,40
2022,Mississippi,GOVERNOR,,Example Democrat,DEM,350
2022,Mississippi,GOVERNOR,,Example Libertarian,LIB,10
2024,Alabama,US SENATE,,Example Republican,REPUBLICAN,400
2024,Alabama,US SENATE,,Example Democrat,DEMOCRAT,500
"""


def test_party_aliases_are_normalized_into_three_groups() -> None:
    assert normalize_party("gop") is VoteParty.REPUBLICAN
    assert normalize_party("REP") is VoteParty.REPUBLICAN
    assert normalize_party("democratic") is VoteParty.DEMOCRAT
    assert normalize_party("Independent") is VoteParty.INDEPENDENT_OTHER
    assert normalize_party("Green") is VoteParty.INDEPENDENT_OTHER


def test_candidate_vote_csv_aggregates_by_state_race_year_and_party() -> None:
    votes = process_election_csv(StringIO(ELECTION_CSV))
    indexed = {(vote.state_fips, vote.year, vote.office, vote.district, vote.party): vote for vote in votes}

    assert indexed[("01", 2020, ElectionOffice.HOUSE, "1", VoteParty.REPUBLICAN)].candidate_votes == 125
    assert indexed[("01", 2020, ElectionOffice.HOUSE, "1", VoteParty.DEMOCRAT)].candidate_votes == 200
    assert indexed[("01", 2020, ElectionOffice.HOUSE, "1", VoteParty.INDEPENDENT_OTHER)].candidate_votes == 25
    assert indexed[("28", 2022, ElectionOffice.GOVERNOR, "", VoteParty.REPUBLICAN)].candidate_votes == 350
    assert indexed[("28", 2022, ElectionOffice.GOVERNOR, "", VoteParty.DEMOCRAT)].candidate_votes == 350
    assert indexed[("01", 2024, ElectionOffice.SENATE, "", VoteParty.REPUBLICAN)].candidate_votes == 400
    assert indexed[("01", 2024, ElectionOffice.SENATE, "", VoteParty.DEMOCRAT)].candidate_votes == 500

    assert sum(vote.candidate_votes for vote in votes if vote.year == 2020) == 350
    assert sum(vote.candidate_votes for vote in votes if vote.year == 2022) == 710
    assert sum(vote.candidate_votes for vote in votes if vote.year == 2024) == 900


def test_candidate_vote_csv_ignores_unrequested_offices() -> None:
    csv_data = StringIO(
        "year,state,office,candidate,party,candidatevotes\n"
        "2024,AL,PRESIDENT,Example Candidate,REP,100\n"
        "2024,AL,GOVERNOR,Example Candidate,REP,40\n"
    )

    votes = process_election_csv(csv_data)

    assert len(votes) == 1
    assert votes[0].office is ElectionOffice.GOVERNOR
    assert votes[0].candidate_votes == 40


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("12.5", "non-negative integer"),
        ("-1", "non-negative integer"),
        ("NaN", "non-negative integer"),
        ("not-a-number", "Invalid candidate vote count"),
    ],
)
def test_election_ingest_rejects_invalid_candidate_vote_counts(value, message) -> None:
    source = StringIO(f"year,state,office,party,candidatevotes\n2024,AL,GOVERNOR,REP,{value}\n")

    with pytest.raises(ValueError, match=message):
        process_election_csv(source)


def test_election_ingest_accepts_source_alias_columns_and_decimal_district() -> None:
    source = StringIO(
        """year,State Abbreviation,Office,District,Party,Candidate Votes
2024,AL,US HOUSE,2.0,DEM,"1,250"
"""
    )

    votes = process_election_csv(source)

    assert len(votes) == 1
    assert votes[0].state_fips == "01"
    assert votes[0].district == "2"
    assert votes[0].candidate_votes == 1250
    assert votes[0].party is VoteParty.DEMOCRAT


def test_election_ingest_reads_utf8_bom_from_csv_path(tmp_path) -> None:
    csv_path = tmp_path / "elections.csv"
    csv_path.write_text(ELECTION_CSV, encoding="utf-8-sig")

    votes = process_election_csv(csv_path)

    assert len(votes) == 8
    independent_house_total = next(
        vote.candidate_votes
        for vote in votes
        if vote.state_fips == "01"
        and vote.year == 2020
        and vote.office is ElectionOffice.HOUSE
        and vote.party is VoteParty.INDEPENDENT_OTHER
    )
    assert independent_house_total == 25


def test_election_ingest_reports_missing_required_csv_column() -> None:
    source = StringIO("year,state,party,candidatevotes\n2024,AL,REP,10\n")

    with pytest.raises(ValueError, match="missing required column: office"):
        process_election_csv(source)


def test_election_cli_reports_nonexistent_file(monkeypatch, capsys, tmp_path) -> None:
    missing_path = tmp_path / "missing.csv"
    monkeypatch.setattr(sys, "argv", ["elections", "--file", str(missing_path)])

    with pytest.raises(SystemExit) as exc_info:
        elections.main()

    assert exc_info.value.code == 1
    assert f"Error: File '{missing_path}' does not exist." in capsys.readouterr().err


def test_election_cli_prints_processed_records(monkeypatch, capsys, tmp_path) -> None:
    input_path = tmp_path / "elections.csv"
    input_path.write_text("synthetic fixture", encoding="utf-8")
    vote = CandidateVoteData(
        state_fips="01",
        year=2024,
        office=ElectionOffice.GOVERNOR,
        party=VoteParty.REPUBLICAN,
        candidate_votes=75,
    )
    monkeypatch.setattr(sys, "argv", ["elections", "--file", str(input_path)])
    monkeypatch.setattr(elections, "process_election_csv", lambda _path: [vote])

    elections.main()

    output = capsys.readouterr().out
    assert "Successfully processed 1 candidate vote records." in output
    assert "candidate_votes=75" in output
