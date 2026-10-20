from datetime import date, datetime, timezone

import pytest
import responses
from responses import matchers

from haze_ingest.cities import City
from haze_ingest.openmeteo import OpenMeteoError, fetch_air_quality
from haze_ingest.session import make_session

URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
PALANGKA = City("Palangka Raya", "Kalimantan Tengah", -2.21, 113.92)
PARAMS = {
    "latitude": "-2.21",
    "longitude": "113.92",
    "hourly": "pm2_5,pm10,us_aqi",
    "start_date": "2026-10-17",
    "end_date": "2026-10-17",
    "timezone": "GMT",
}


def body(**hourly):
    data = {
        "time": ["2026-10-17T00:00", "2026-10-17T01:00"],
        "pm2_5": [61.5, 60.1],
        "pm10": [80.0, 79.2],
        "us_aqi": [154, 153],
    }
    data.update(hourly)
    return {"latitude": -2.199997, "longitude": 113.899994, "hourly": data}


def mock(status=200, json=None):
    responses.get(URL, status=status, json=json, match=[matchers.query_param_matcher(PARAMS)])


def fetch():
    return fetch_air_quality(make_session(), PALANGKA, date(2026, 10, 17), date(2026, 10, 17))


@responses.activate
def test_parses_hours_as_utc():
    mock(json=body())
    rows = fetch()
    assert rows[0].time == datetime(2026, 10, 17, 0, tzinfo=timezone.utc)
    assert rows[0].date == date(2026, 10, 17)
    assert rows[0].city == "Palangka Raya" and rows[0].grid_latitude == -2.199997
    assert rows[1].pm2_5 == 60.1


@responses.activate
def test_nulls_kept_as_none():
    mock(json=body(pm2_5=[None, 60.1]))
    assert fetch()[0].pm2_5 is None


@responses.activate
def test_ragged_arrays_raise():
    mock(json=body(pm10=[80.0]))
    with pytest.raises(OpenMeteoError, match="Palangka Raya"):
        fetch()


@responses.activate
def test_api_error_reason_surfaces():
    reason = "Parameter 'end_date' is out of allowed range"
    mock(status=400, json={"error": True, "reason": reason})
    with pytest.raises(OpenMeteoError) as exc:
        fetch()
    assert reason in str(exc.value) and "Palangka Raya" in str(exc.value)


@responses.activate
def test_negative_pm25_rejected():
    mock(json=body(pm2_5=[-1.0, 60.1]))
    with pytest.raises(OpenMeteoError):
        fetch()
