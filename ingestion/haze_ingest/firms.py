import csv
import io
from datetime import date
from typing import Literal

import requests
from google.cloud import bigquery
from pydantic import BaseModel, Field, ValidationError, field_validator

from haze_ingest.session import TIMEOUT

SOURCE = "VIIRS_SNPP_NRT"
AREA = "95,-11,141,6"
MAX_DAY_RANGE = 5
BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight"


class FirmsError(Exception):
    pass


class Hotspot(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    bright_ti4: float
    scan: float
    track: float
    acq_date: date
    acq_time: str
    satellite: str
    instrument: str
    confidence: Literal["l", "n", "h"]
    version: str
    bright_ti5: float
    frp: float
    daynight: Literal["D", "N"]

    @field_validator("acq_time")
    @classmethod
    def pad_hhmm(cls, value: str) -> str:
        if not (value.isdigit() and 1 <= len(value) <= 4):
            raise ValueError("acq_time must be 1-4 digits (HHMM)")
        padded = value.zfill(4)
        if int(padded[:2]) > 23 or int(padded[2:]) > 59:
            raise ValueError("acq_time out of range")
        return padded


_BQ_TYPES = {float: "FLOAT64", date: "DATE"}
HOTSPOT_SCHEMA = [
    bigquery.SchemaField(name, _BQ_TYPES.get(field.annotation, "STRING"), mode="REQUIRED")
    for name, field in Hotspot.model_fields.items()
] + [bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED")]


def fetch_hotspots(session: requests.Session, map_key: str, start: date, day_range: int) -> list[Hotspot]:
    # The key is part of the URL, so errors carry only the window, never the URL or the original exception.
    window = f"{start} (+{day_range}d)"
    url = f"{BASE_URL}/{map_key}/{SOURCE}/{AREA}/{day_range}/{start.isoformat()}"
    try:
        response = session.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise FirmsError(f"FIRMS request failed for {window}: {type(e).__name__}") from None
    if response.status_code != 200:
        raise FirmsError(f"FIRMS request failed for {window}: HTTP {response.status_code}: {response.text[:100]}")

    text = response.text
    if text.split("\n", 1)[0].strip() != HEADER:
        raise FirmsError(f"FIRMS returned a non-CSV response for {window}: {text[:100]!r}")

    hotspots = []
    for line, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            hotspots.append(Hotspot(**row))
        except ValidationError as e:
            raise FirmsError(f"FIRMS row invalid at line {line} for {window}: {e.errors()[0]['msg']}") from None
    return hotspots
