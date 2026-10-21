import logging
from datetime import date, datetime, timezone

import pytest

import haze_ingest.__main__ as cli
from haze_ingest.cities import City
from haze_ingest.config import Settings
from haze_ingest.firms import Hotspot
from haze_ingest.openmeteo import AirQualityHour, OpenMeteoError

TODAY = date(2026, 10, 20)
NOW = datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc)
SETTINGS = Settings(firms_map_key="KEY123", gcp_project_id="p")
CITIES = [City("A", "PA", -1.0, 110.0), City("B", "PB", -2.0, 111.0)]
DAYS = [date(2026, 10, 17), date(2026, 10, 18), date(2026, 10, 19)]


def hotspot(day):
    return Hotspot(
        latitude=-2.5, longitude=113.9, bright_ti4=330.1, scan=0.4, track=0.4, acq_date=day, acq_time="518",
        satellite="N", instrument="VIIRS", confidence="n", version="2.0NRT", bright_ti5=295.0, frp=4.4, daynight="D",
    )


def air(city, day):
    t = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return AirQualityHour(
        city=city.name, grid_latitude=city.latitude, grid_longitude=city.longitude, time=t, date=day,
        pm2_5=60.0, pm10=80.0, us_aqi=150,
    )


def test_default_window_is_three_completed_days():
    assert cli.default_window(TODAY) == (date(2026, 10, 17), date(2026, 10, 19))


@pytest.mark.parametrize("start,end,match", [
    (date(2026, 10, 18), date(2026, 10, 20), "2026-10-20"),
    (date(2026, 8, 21), date(2026, 10, 19), "2026-08-21"),
    (date(2026, 10, 19), date(2026, 10, 18), "after"),
])
def test_validate_window_rejects(start, end, match):
    with pytest.raises(ValueError, match=match):
        cli.validate_window(start, end, TODAY)


def test_validate_window_accepts_59_day_backfill():
    cli.validate_window(date(2026, 8, 22), date(2026, 10, 19), TODAY)


def test_firms_chunks_cover_window_in_fives():
    assert cli.firms_chunks(date(2026, 10, 1), date(2026, 10, 12)) == [
        (date(2026, 10, 1), 5), (date(2026, 10, 6), 5), (date(2026, 10, 11), 2)]


def test_run_loads_both_tables_for_every_date(monkeypatch, fake):
    monkeypatch.setattr(cli, "fetch_hotspots", lambda session, key, start, n: [hotspot(d) for d in DAYS])
    monkeypatch.setattr(cli, "fetch_air_quality", lambda session, city, start, end: [air(city, d) for d in DAYS])
    cli.run(SETTINGS, None, fake, CITIES, DAYS[0], DAYS[-1], NOW)
    destinations = [c.destination for c in fake.loads]
    for table in ("p.raw.firms_hotspots", "p.raw.air_quality_hourly"):
        assert [d for d in destinations if d.startswith(table + "$")] == [f"{table}$2026101{n}" for n in (7, 8, 9)]
    assert all(row["ingested_at"] == NOW.isoformat() for c in fake.loads for row in c.rows)


def test_run_loads_nothing_when_a_fetch_fails(monkeypatch, fake):
    def fail_on_second(session, city, start, end):
        if city is CITIES[1]:
            raise OpenMeteoError("Open-Meteo request failed for B: HTTP 500")
        return [air(city, d) for d in DAYS]

    monkeypatch.setattr(cli, "fetch_hotspots", lambda session, key, start, n: [hotspot(d) for d in DAYS])
    monkeypatch.setattr(cli, "fetch_air_quality", fail_on_second)
    with pytest.raises(OpenMeteoError):
        cli.run(SETTINGS, None, fake, CITIES, DAYS[0], DAYS[-1], NOW)
    assert fake.loads == [] and fake.deleted == []


def test_main_returns_1_on_bad_window(monkeypatch, caplog):
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY123")
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    assert cli.main(["--start", "2026-10-19", "--end", "2026-10-18"]) == 1
    assert "after" in caplog.text


def test_main_silences_urllib3_retry_warnings(monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY123")
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    logging.getLogger("urllib3").setLevel(logging.NOTSET)
    cli.main(["--start", "2026-10-19", "--end", "2026-10-18"])
    assert logging.getLogger("urllib3").getEffectiveLevel() >= logging.ERROR


def test_main_returns_1_without_gcp_credentials(monkeypatch, caplog):
    from google.auth.exceptions import DefaultCredentialsError

    def no_credentials(project):
        raise DefaultCredentialsError("Your default credentials were not found.")

    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY123")
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setattr(cli.bigquery, "Client", no_credentials)
    assert cli.main([]) == 1
    assert "GOOGLE_APPLICATION_CREDENTIALS" in caplog.text


def test_run_validates_both_tables_before_loading_either(monkeypatch, fake):
    monkeypatch.setattr(cli, "fetch_hotspots", lambda session, key, start, n: [hotspot(d) for d in DAYS])
    monkeypatch.setattr(cli, "fetch_air_quality", lambda session, city, start, end: [air(city, date(2026, 10, 20))])
    with pytest.raises(ValueError, match="2026-10-20"):
        cli.run(SETTINGS, None, fake, CITIES, DAYS[0], DAYS[-1], NOW)
    assert fake.loads == [] and fake.deleted == []


@pytest.mark.parametrize("error", [
    pytest.param(__import__("google.api_core.exceptions", fromlist=["Forbidden"]).Forbidden("quota"), id="google-api"),
    pytest.param(__import__("concurrent.futures", fromlist=["TimeoutError"]).TimeoutError(), id="job-timeout"),
])
def test_main_returns_1_on_bigquery_failure(monkeypatch, caplog, error):
    def failing_run(*args):
        raise error

    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY123")
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setattr(cli.bigquery, "Client", lambda project: object())
    monkeypatch.setattr(cli, "run", failing_run)
    assert cli.main([]) == 1
    assert "BigQuery" in caplog.text


def test_main_credentials_error_keeps_cause(monkeypatch, caplog):
    from google.auth.exceptions import DefaultCredentialsError

    def missing_file(project):
        raise DefaultCredentialsError("File secrets/loader-sa.json was not found.")

    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY123")
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setattr(cli.bigquery, "Client", missing_file)
    assert cli.main([]) == 1
    assert "secrets/loader-sa.json was not found" in caplog.text


def test_main_returns_1_when_key_file_is_unreadable(monkeypatch, caplog):
    def unreadable(project):
        raise PermissionError(13, "Permission denied", "/opt/pipeline/secrets/loader-sa.json")

    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY123")
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setattr(cli.bigquery, "Client", unreadable)
    assert cli.main([]) == 1
    assert "/opt/pipeline/secrets/loader-sa.json" in caplog.text
    assert "AIRFLOW_UID" in caplog.text
