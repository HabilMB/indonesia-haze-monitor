import datetime as dt

import requests
from google.cloud import bigquery
from pydantic import BaseModel, Field, ValidationError

from haze_ingest.cities import City
from haze_ingest.session import TIMEOUT

URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
HOURLY = ("pm2_5", "pm10", "us_aqi")


class OpenMeteoError(Exception):
    pass


class AirQualityHour(BaseModel):
    city: str
    grid_latitude: float
    grid_longitude: float
    time: dt.datetime
    date: dt.date
    pm2_5: float | None = Field(ge=0)
    pm10: float | None = Field(ge=0)
    us_aqi: int | None = Field(ge=0)


AIR_QUALITY_SCHEMA = [
    bigquery.SchemaField("city", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("grid_latitude", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("grid_longitude", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("time", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("pm2_5", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("pm10", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("us_aqi", "INT64", mode="NULLABLE"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
]


def fetch_air_quality(session: requests.Session, city: City, start: dt.date, end: dt.date) -> list[AirQualityHour]:
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "hourly": ",".join(HOURLY),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "GMT",
    }
    try:
        response = session.get(URL, params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise OpenMeteoError(f"Open-Meteo request failed for {city.name}: {type(e).__name__}") from None
    if response.status_code != 200:
        try:
            reason = response.json().get("reason", response.text[:100])
        except ValueError:
            reason = response.text[:100]
        raise OpenMeteoError(f"Open-Meteo request failed for {city.name}: HTTP {response.status_code}: {reason}")

    try:
        data = response.json()
        times = data["hourly"]["time"]
        columns = {name: data["hourly"][name] for name in HOURLY}
        grid_latitude, grid_longitude = data["latitude"], data["longitude"]
    except (ValueError, KeyError, TypeError) as e:
        raise OpenMeteoError(f"Open-Meteo returned an unexpected response for {city.name}: {type(e).__name__}") from None
    if any(len(values) != len(times) for values in columns.values()):
        raise OpenMeteoError(f"Open-Meteo returned arrays of different lengths for {city.name}")

    rows = []
    for i, raw_time in enumerate(times):
        time = dt.datetime.fromisoformat(raw_time).replace(tzinfo=dt.timezone.utc)
        try:
            rows.append(
                AirQualityHour(
                    city=city.name,
                    grid_latitude=grid_latitude,
                    grid_longitude=grid_longitude,
                    time=time,
                    date=time.date(),
                    **{name: values[i] for name, values in columns.items()},
                )
            )
        except ValidationError as e:
            raise OpenMeteoError(f"Open-Meteo value invalid for {city.name} at {raw_time}: {e.errors()[0]['msg']}") from None
    return rows
