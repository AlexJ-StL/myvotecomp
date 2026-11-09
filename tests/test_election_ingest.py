from io import StringIO

from ingest.elections import normalize_party, process_election_csv
from models import ElectionOffice, VoteParty

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
    indexed = {
        (vote.state_fips, vote.year, vote.office, vote.district, vote.party): vote
        for vote in votes
    }

    assert (
        indexed[
            ("01", 2020, ElectionOffice.HOUSE, "1", VoteParty.REPUBLICAN)
        ].candidate_votes
        == 125
    )
    assert (
        indexed[
            ("01", 2020, ElectionOffice.HOUSE, "1", VoteParty.DEMOCRAT)
        ].candidate_votes
        == 200
    )
    assert (
        indexed[
            ("01", 2020, ElectionOffice.HOUSE, "1", VoteParty.INDEPENDENT_OTHER)
        ].candidate_votes
        == 25
    )
    assert (
        indexed[
            ("28", 2022, ElectionOffice.GOVERNOR, "", VoteParty.REPUBLICAN)
        ].candidate_votes
        == 350
    )
    assert (
        indexed[
            ("28", 2022, ElectionOffice.GOVERNOR, "", VoteParty.DEMOCRAT)
        ].candidate_votes
        == 350
    )
    assert (
        indexed[
            ("01", 2024, ElectionOffice.SENATE, "", VoteParty.REPUBLICAN)
        ].candidate_votes
        == 400
    )
    assert (
        indexed[
            ("01", 2024, ElectionOffice.SENATE, "", VoteParty.DEMOCRAT)
        ].candidate_votes
        == 500
    )

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
