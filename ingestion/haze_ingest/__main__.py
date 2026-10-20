import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

import requests
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from haze_ingest.cities import City, load_cities
from haze_ingest.config import ConfigError, Settings
from haze_ingest.firms import HOTSPOT_SCHEMA, MAX_DAY_RANGE, FirmsError, fetch_hotspots
from haze_ingest.load import ensure_table, group_by_date, load_partitions
from haze_ingest.openmeteo import AIR_QUALITY_SCHEMA, OpenMeteoError, fetch_air_quality
from haze_ingest.session import make_session

HOTSPOT_TABLE = "{project}.raw.firms_hotspots"
AIR_QUALITY_TABLE = "{project}.raw.air_quality_hourly"
MAX_DAYS_BACK = 59

log = logging.getLogger("haze_ingest")


def default_window(today: date) -> tuple[date, date]:
    return today - timedelta(days=3), today - timedelta(days=1)


def validate_window(start: date, end: date, today: date) -> None:
    if start > end:
        raise ValueError(f"--start {start} is after --end {end}.")
    if end >= today:
        raise ValueError(f"--end {end} must be before today ({today}, UTC); today's data is incomplete.")
    oldest = today - timedelta(days=MAX_DAYS_BACK)
    if start < oldest:
        raise ValueError(f"--start {start} is older than {oldest}; sandbox partitions expire after 60 days.")


def firms_chunks(start: date, end: date) -> list[tuple[date, int]]:
    chunks = []
    while start <= end:
        day_range = min(MAX_DAY_RANGE, (end - start).days + 1)
        chunks.append((start, day_range))
        start += timedelta(days=day_range)
    return chunks


def run(
    settings: Settings,
    session: requests.Session,
    client: bigquery.Client,
    cities: list[City],
    start: date,
    end: date,
    now: datetime,
) -> None:
    # Fetch everything before loading anything, so a failed fetch never leaves half a window loaded.
    hotspots = [
        h for chunk_start, day_range in firms_chunks(start, end)
        for h in fetch_hotspots(session, settings.firms_map_key, chunk_start, day_range)
    ]
    air_quality = [row for city in cities for row in fetch_air_quality(session, city, start, end)]

    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    ingested_at = now.isoformat()
    tables = []
    for table, schema, models, partition_field, clustering in (
        (HOTSPOT_TABLE, HOTSPOT_SCHEMA, hotspots, "acq_date", None),
        (AIR_QUALITY_TABLE, AIR_QUALITY_SCHEMA, air_quality, "date", ["city"]),
    ):
        table_id = table.format(project=settings.gcp_project_id)
        rows = [{**m.model_dump(mode="json"), "ingested_at": ingested_at} for m in models]
        group_by_date(rows, partition_field, dates, table_id)  # validate both tables before writing either
        tables.append((table_id, schema, rows, partition_field, clustering))

    # No transactions without DML: a BigQuery failure here can leave one table newer than the other; rerunning heals it.
    for table_id, schema, rows, partition_field, clustering in tables:
        ensure_table(client, table_id, schema, partition_field, clustering)
        counts = load_partitions(client, table_id, schema, rows, partition_field, dates)
        log.info("%s rows per date: %s", table_id, {str(d): n for d, n in counts.items()})


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # urllib3 logs retries with the request path, which contains the FIRMS key.
    logging.getLogger("urllib3").setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(prog="haze_ingest", description="Load FIRMS hotspots and Open-Meteo air quality into BigQuery raw.")
    parser.add_argument("--start", type=date.fromisoformat, help="first UTC date (YYYY-MM-DD); default: 3 days ago")
    parser.add_argument("--end", type=date.fromisoformat, help="last UTC date (YYYY-MM-DD); default: yesterday")
    args = parser.parse_args(argv)
    if (args.start is None) != (args.end is None):
        parser.error("--start and --end must be given together")

    now = datetime.now(timezone.utc)
    today = now.date()
    try:
        settings = Settings.from_env()
        start, end = (args.start, args.end) if args.start else default_window(today)
        validate_window(start, end, today)
        try:
            client = bigquery.Client(project=settings.gcp_project_id)
        except DefaultCredentialsError as e:
            raise ConfigError(f"No GCP credentials found ({e}). Set GOOGLE_APPLICATION_CREDENTIALS to the loader service-account JSON (see .env.example).") from None
        run(settings, make_session(), client, load_cities(), start, end, now)
    except (ConfigError, FirmsError, OpenMeteoError, ValueError) as e:
        log.error("%s", e)
        return 1
    except (GoogleAPIError, TimeoutError) as e:
        log.error("BigQuery failed: %s: %s. Loads are idempotent; rerun the same window.", type(e).__name__, e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
