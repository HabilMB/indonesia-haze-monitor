import csv
from dataclasses import dataclass
from pathlib import Path

CITIES_CSV = Path(__file__).resolve().parents[2] / "dbt" / "seeds" / "cities.csv"


@dataclass(frozen=True)
class City:
    name: str
    province: str
    latitude: float
    longitude: float


def load_cities(path: Path = CITIES_CSV) -> list[City]:
    with path.open(newline="") as f:
        return [
            City(row["city"], row["province"], float(row["latitude"]), float(row["longitude"]))
            for row in csv.DictReader(f)
        ]
