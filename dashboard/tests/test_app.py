from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import loaders
from shape import combine_history

APP = str(Path(__file__).resolve().parents[1] / "app.py")
CITIES = [("palangka_raya", "Palangka Raya", -2.21, 113.92), ("jambi", "Jambi", -1.61, 103.61), ("jakarta", "Jakarta", -6.21, 106.85)]
PM = {"palangka_raya": 500.0, "jambi": 80.0, "jakarta": 90.0}
DATES = pd.date_range("2026-10-15", "2026-10-19").strftime("%Y-%m-%d")


def city_day():
    rows = [
        {"city_date_id": f"{c}|{d}", "city_id": c, "city_name": n, "province": "P", "date_utc": d,
         "pm2_5_mean": PM[c] + i, "pm2_5_max": PM[c] * 2, "us_aqi_max": 300, "hours_observed": 24,
         "hotspots_100km": 10 * i, "hotspots_250km": 30 * i}
        for i, d in enumerate(DATES) for c, n, _, _ in CITIES
    ]
    return combine_history(pd.DataFrame(rows), pd.DataFrame())


def cities():
    return pd.DataFrame([{"city_id": c, "city_name": n, "province": "P", "latitude": la, "longitude": lo} for c, n, la, lo in CITIES])


def hotspots():
    return pd.DataFrame({"latitude": [-2.3, -2.0, -1.7, -1.5], "longitude": [113.8, 114.0, 103.5, 103.7],
                         "acq_date": ["2026-10-19"] * 4, "frp": [4.0, 10.0, 2.5, 7.0]})


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(loaders, "load_city_day", city_day)
    monkeypatch.setattr(loaders, "load_cities", cities)
    monkeypatch.setattr(loaders, "load_recent_hotspots", hotspots)
    return AppTest.from_file(APP, default_timeout=30)


def texts(elements):
    return " ".join(str(e.value) for e in elements)


def test_app_renders_without_exceptions(app):
    app.run()
    assert not app.exception
    assert app.title[0].value == "Indonesia Haze Monitor"
    assert "Data through 2026-10-19 (UTC)" in texts(app.caption)


def test_worst_city_is_latest_day_max_pm25(app):
    app.run()
    assert "Palangka Raya" in texts(app.subheader)
    assert app.selectbox[0].value == "Palangka Raya"


def test_map_note_when_no_recent_hotspots(app, monkeypatch):
    monkeypatch.setattr(loaders, "load_recent_hotspots", lambda: hotspots().iloc[0:0])
    app.run()
    assert not app.exception
    assert "No nominal/high-confidence hotspots in the last 3 days" in texts(app.caption)


def test_missing_config_shows_error(app, monkeypatch):
    def missing():
        raise loaders.MissingConfig("Set gcp_project_id in Streamlit secrets or the GCP_PROJECT_ID env var.")

    monkeypatch.setattr(loaders, "load_city_day", missing)
    app.run()
    assert not app.exception
    assert "GCP_PROJECT_ID" in app.error[0].value


@pytest.mark.parametrize("error", [
    pytest.param(__import__("google.api_core.exceptions", fromlist=["Forbidden"]).Forbidden("Access Denied: Table p:marts.city_day"), id="forbidden"),
    pytest.param(TimeoutError(), id="timeout"),
])
def test_bigquery_failure_shows_friendly_error_without_details(app, monkeypatch, error):
    def failing():
        raise error

    monkeypatch.setattr(loaders, "load_city_day", failing)
    app.run()
    assert not app.exception
    assert "temporarily unavailable" in app.error[0].value
    assert "marts" not in app.error[0].value
