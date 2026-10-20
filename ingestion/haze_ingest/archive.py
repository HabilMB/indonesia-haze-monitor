"""Archive marts.city_day to CSV so the haze season outlives the sandbox's 60-day partition expiry."""
import csv
import logging
import sys
from collections import defaultdict
from pathlib import Path

from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery

from haze_ingest.config import ConfigError, Settings

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DAILY_CSV = DATA_DIR / "city_day_daily.csv"
MONTHLY_CSV = DATA_DIR / "city_day_monthly.csv"

DAILY_TYPES = {
    "city_date_id": str, "city_id": str, "city_name": str, "province": str, "date_utc": str,
    "pm2_5_mean": float, "pm2_5_max": float, "us_aqi_max": int, "hours_observed": int,
    "hotspots_100km": int, "hotspots_250km": int,
}

log = logging.getLogger("haze_ingest.archive")


def merge_daily(archived: list[dict], fresh: list[dict]) -> list[dict]:
    by_id = {row["city_date_id"]: row for row in archived}
    by_id.update({row["city_date_id"]: row for row in fresh})
    return sorted(by_id.values(), key=lambda r: (r["date_utc"], r["city_id"]))


def monthly(daily: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in daily:
        groups[(row["city_id"], row["date_utc"][:7])].append(row)
    out = []
    for (city_id, month), rows in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        pm = [r["pm2_5_mean"] for r in rows if r["pm2_5_mean"] is not None]
        out.append({
            "city_id": city_id,
            "city_name": rows[0]["city_name"],
            "month": month,
            "days": len(rows),
            "pm2_5_mean": round(sum(pm) / len(pm), 2) if pm else None,
            "pm2_5_worst_day": max(pm) if pm else None,
            "hotspots_100km": sum(r["hotspots_100km"] for r in rows),
            "hotspots_250km": sum(r["hotspots_250km"] for r in rows),
        })
    return out


def read_daily(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [
            {k: (DAILY_TYPES[k](v) if v != "" else None) for k, v in row.items()}
            for row in csv.DictReader(f)
        ]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fetch_city_day(client: bigquery.Client, project: str) -> list[dict]:
    rows = client.query(f"select * from `{project}.marts.city_day`").result(timeout=120)
    return [
        {
            name: (round(row[name], 2) if cast is float and row[name] is not None
                   else row[name].isoformat() if name == "date_utc" else row[name])
            for name, cast in DAILY_TYPES.items()
        }
        for row in rows
    ]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = Settings.from_env()
        fresh = fetch_city_day(bigquery.Client(project=settings.gcp_project_id), settings.gcp_project_id)
    except (ConfigError, GoogleAPIError, TimeoutError) as e:
        log.error("%s", e)
        return 1
    daily = merge_daily(read_daily(DAILY_CSV), fresh)
    write_csv(DAILY_CSV, daily)
    write_csv(MONTHLY_CSV, monthly(daily))
    log.info("archived %d city-days (%s..%s), %d fetched", len(daily), daily[0]["date_utc"], daily[-1]["date_utc"], len(fresh))
    return 0


if __name__ == "__main__":
    sys.exit(main())
