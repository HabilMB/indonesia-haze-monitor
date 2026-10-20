from haze_ingest.archive import merge_daily, monthly


def day(city_id, date_utc, pm, h100, h250, **extra):
    return {
        "city_date_id": f"{city_id}|{date_utc}", "city_id": city_id, "city_name": city_id.title(),
        "province": "P", "date_utc": date_utc, "pm2_5_mean": pm, "pm2_5_max": pm, "us_aqi_max": 100,
        "hours_observed": 24, "hotspots_100km": h100, "hotspots_250km": h250, **extra,
    }


def test_merge_keeps_expired_days_and_takes_fresh_values():
    archived = [day("jambi", "2026-08-21", 50.0, 1, 2), day("jambi", "2026-10-19", 60.0, 3, 4)]
    fresh = [day("jambi", "2026-10-19", 61.0, 3, 5), day("jambi", "2026-10-20", 70.0, 0, 0)]
    merged = merge_daily(archived, fresh)
    assert [r["date_utc"] for r in merged] == ["2026-08-21", "2026-10-19", "2026-10-20"]
    assert merged[1]["pm2_5_mean"] == 61.0 and merged[1]["hotspots_250km"] == 5


def test_merge_sorts_by_date_then_city():
    merged = merge_daily([], [day("pontianak", "2026-10-01", 1.0, 0, 0), day("jambi", "2026-10-01", 1.0, 0, 0)])
    assert [r["city_id"] for r in merged] == ["jambi", "pontianak"]


def test_monthly_aggregates_per_city_and_month():
    rows = [
        day("jambi", "2026-09-29", 100.0, 1, 10),
        day("jambi", "2026-09-30", 200.0, 2, 20),
        day("jambi", "2026-10-01", 50.0, 0, 5),
    ]
    assert monthly(rows) == [
        {"city_id": "jambi", "city_name": "Jambi", "month": "2026-09", "days": 2,
         "pm2_5_mean": 150.0, "pm2_5_worst_day": 200.0, "hotspots_100km": 3, "hotspots_250km": 30},
        {"city_id": "jambi", "city_name": "Jambi", "month": "2026-10", "days": 1,
         "pm2_5_mean": 50.0, "pm2_5_worst_day": 50.0, "hotspots_100km": 0, "hotspots_250km": 5},
    ]


def test_monthly_ignores_days_without_pm25():
    rows = [day("jambi", "2026-10-01", None, 1, 1), day("jambi", "2026-10-02", 40.0, 1, 1)]
    (m,) = monthly(rows)
    assert m["days"] == 2 and m["pm2_5_mean"] == 40.0 and m["pm2_5_worst_day"] == 40.0
