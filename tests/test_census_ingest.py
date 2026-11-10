from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

import ingest.census as census
from ingest.census import fetch_census_demographics
from models import DemographicRecordData


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


def _client_for(payload: object, status_code: int = 200) -> httpx.Client:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload, request=request)

    return httpx.Client(transport=httpx.MockTransport(respond))


def test_census_rejects_http_errors_without_exposing_response_body() -> None:
    with _client_for({"error": "sensitive upstream detail"}, 503) as client:
        with pytest.raises(RuntimeError, match="status 503") as exc_info:
            fetch_census_demographics(2024, "test-key", client)

    assert "sensitive upstream detail" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "invalid tabular response"),
        (["not-a-header"], "missing its header row"),
        ([["state"]], "missing variables"),
    ],
)
def test_census_rejects_invalid_headers(payload: object, message: str) -> None:
    with _client_for(payload) as client:
        with pytest.raises(ValueError, match=message):
            fetch_census_demographics(2024, "test-key", client)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.__setitem__(1, ["short row"]), "malformed data row"),
        (
            lambda payload: payload[1].__setitem__(1, "not-a-count"),
            "B01001_001E is not an integer",
        ),
        (
            lambda payload: payload[1].__setitem__(2, "-1"),
            "B01001_007E is negative",
        ),
    ],
)
def test_census_rejects_malformed_rows_and_population_counts(
    mutate, message: str
) -> None:
    payload = census_response()
    mutate(payload)

    with _client_for(payload) as client:
        with pytest.raises(ValueError, match=message):
            fetch_census_demographics(2024, "test-key", client)


def test_census_fetch_owns_and_closes_client_when_none_is_supplied(monkeypatch) -> None:
    state = {"closed": False, "timeout": None}

    class Client:
        def __init__(self, *, timeout: float) -> None:
            state["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_exc_info) -> None:
            state["closed"] = True

        def get(
            self, url: str, *, params: dict[str, str | list[str]]
        ) -> httpx.Response:
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(200, json=census_response(), request=request)

    monkeypatch.setattr(census.httpx, "Client", Client)

    records = fetch_census_demographics(2024, "test-key")

    assert len(records) == 2
    assert state == {"closed": True, "timeout": 30.0}


def test_census_cli_loads_key_and_prints_records(monkeypatch, capsys) -> None:
    record = DemographicRecordData(
        state_fips="01",
        year=2024,
        total_population=100,
        working_age_18_64=60,
        population_18_plus=80,
    )
    monkeypatch.setattr(
        census,
        "get_settings",
        lambda: SimpleNamespace(CENSUS_API_KEY=SecretStr("key")),
    )
    fetch_calls = []

    def fake_fetch(*, year: int, api_key: str):
        fetch_calls.append((year, api_key))
        return [record]

    monkeypatch.setattr(census, "fetch_census_demographics", fake_fetch)
    monkeypatch.setattr(census.sys, "argv", ["census", "--year", "2020"])

    census.main()

    assert fetch_calls == [(2020, "key")]
    output = capsys.readouterr().out
    assert "Successfully retrieved demographic records for 1 states." in output
    assert "state_fips='01'" in output


def test_census_cli_exits_when_settings_are_unavailable(monkeypatch, capsys) -> None:
    def fail_settings():
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(census, "get_settings", fail_settings)
    monkeypatch.setattr(census.sys, "argv", ["census"])

    with pytest.raises(SystemExit) as exc_info:
        census.main()

    assert exc_info.value.code == 1
    assert "settings unavailable" in capsys.readouterr().err
