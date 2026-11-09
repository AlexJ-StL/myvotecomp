import httpx

from ingest.census import fetch_census_demographics


def census_response() -> list[list[str]]:
    age_variables = [
        *(f"B01001_{number:03d}E" for number in range(7, 26)),
        *(f"B01001_{number:03d}E" for number in range(31, 50)),
    ]
    male_18_64 = [10, 10, 10, 30, 50, 50, 40, 40, 30, 30, 20, 10, 10]
    male_65_plus = [10, 10, 10, 5, 3, 2]
    female_18_64 = [10, 10, 10, 30, 60, 60, 40, 40, 30, 30, 20, 10, 10]
    female_65_plus = [12, 12, 10, 6, 5, 5]
    counts = male_18_64 + male_65_plus + female_18_64 + female_65_plus
    header = ["NAME", "B01001_001E", *age_variables, "state"]
    alabama = ["Alabama", "1000", *(str(value) for value in counts), "01"]
    mississippi = ["Mississippi", "900", *(str(value // 2) for value in counts), "28"]
    return [header, alabama, mississippi]


def test_census_fetch_calculates_population_and_preserves_state_fips() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=census_response(), request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        records = fetch_census_demographics(
            year=2024,
            api_key="synthetic-census-key",
            client=client,
        )

    alabama, mississippi = records
    assert requests[0].url.params["key"] == "synthetic-census-key"
    assert "B01001_001E" in requests[0].url.params["get"]
    assert alabama.state_fips == "01"
    assert alabama.year == 2024
    assert alabama.total_population == 1000
    assert alabama.working_age_18_64 == 700
    assert alabama.population_18_plus == 790
    assert mississippi.state_fips == "28"
    assert mississippi.total_population == 900
