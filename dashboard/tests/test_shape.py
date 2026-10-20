import pandas as pd

from shape import combine_history, latest_snapshot, ring_breakdown, season_ranking


def rows(*specs):
    """specs: (city_id, date, pm2_5_mean, hotspots_100km, hotspots_250km)"""
    return pd.DataFrame([
        {"city_date_id": f"{c}|{d}", "city_id": c, "city_name": c.title(), "province": "P",
         "date_utc": d, "pm2_5_mean": pm, "pm2_5_max": pm, "us_aqi_max": 100, "hours_observed": 24,
         "hotspots_100km": h100, "hotspots_250km": h250}
        for c, d, pm, h100, h250 in specs
    ])


def test_combine_prefers_bigquery_and_keeps_expired_archive_days():
    archive = rows(("jambi", "2026-08-21", 50.0, 1, 2), ("jambi", "2026-10-19", 60.0, 1, 2))
    bq = rows(("jambi", "2026-10-19", 61.0, 1, 2), ("jambi", "2026-10-20", 70.0, 0, 0))
    out = combine_history(bq, archive)
    assert [d.strftime("%m-%d") for d in out["date_utc"]] == ["08-21", "10-19", "10-20"]
    assert out.loc[out["date_utc"] == "2026-10-19", "pm2_5_mean"].item() == 61.0
    assert pd.api.types.is_datetime64_any_dtype(out["date_utc"])


def test_combine_with_empty_archive_returns_bigquery_rows():
    bq = rows(("jambi", "2026-10-20", 70.0, 0, 0))
    assert len(combine_history(bq, bq.iloc[0:0])) == 1


def test_latest_snapshot_uses_latest_date_and_sorts_by_pm25():
    city_day = combine_history(rows(
        ("jambi", "2026-10-19", 80.0, 1, 2),
        ("pontianak", "2026-10-19", 120.0, 3, 4),
        ("merauke", "2026-10-18", 999.0, 0, 0),
    ), rows())
    date, snapshot = latest_snapshot(city_day)
    assert date == pd.Timestamp("2026-10-19")
    assert list(snapshot["city_id"]) == ["pontianak", "jambi"]


def test_ring_breakdown_outer_ring_is_difference():
    out = ring_breakdown(combine_history(rows(("jambi", "2026-10-19", 80.0, 3, 10)), rows()))
    assert list(zip(out["ring"], out["hotspots"])) == [("within 100 km", 3), ("100–250 km", 7)]


def test_season_ranking_means_daily_means_and_sums_hotspots():
    city_day = combine_history(rows(
        ("jambi", "2026-10-18", 10.0, 1, 5),
        ("jambi", "2026-10-19", 30.0, 2, 6),
        ("pontianak", "2026-10-19", 50.0, 0, 1),
    ), rows())
    out = season_ranking(city_day)
    assert list(out["city_name"]) == ["Pontianak", "Jambi"]
    assert out.set_index("city_name").loc["Jambi", "pm2_5_mean"] == 20.0
    assert out.set_index("city_name").loc["Jambi", "hotspots_250km"] == 11
