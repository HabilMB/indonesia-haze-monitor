"""Pure pandas shaping for the dashboard. No Streamlit or BigQuery here, so it is unit-tested directly."""
import pandas as pd

RING_INNER = "within 100 km"
RING_OUTER = "100–250 km"


def combine_history(bq: pd.DataFrame, archive: pd.DataFrame) -> pd.DataFrame:
    """BigQuery rows win; archive rows fill only the days the sandbox has already expired."""
    bq = bq.assign(date_utc=pd.to_datetime(bq["date_utc"]))
    if not archive.empty:
        archive = archive.assign(date_utc=pd.to_datetime(archive["date_utc"]))
        older = archive[archive["date_utc"] < bq["date_utc"].min()] if not bq.empty else archive
        bq = pd.concat([older, bq], ignore_index=True)
    return bq.sort_values(["date_utc", "city_id"], ignore_index=True)


def latest_snapshot(city_day: pd.DataFrame) -> tuple[pd.Timestamp, pd.DataFrame]:
    latest = city_day["date_utc"].max()
    snapshot = city_day[city_day["date_utc"] == latest]
    return latest, snapshot.sort_values("pm2_5_mean", ascending=False, ignore_index=True)


def ring_breakdown(city_day: pd.DataFrame) -> pd.DataFrame:
    """Long format for stacked bars; the outer ring excludes the inner one so heights sum to hotspots_250km."""
    inner = city_day.assign(ring=RING_INNER, hotspots=city_day["hotspots_100km"])
    outer = city_day.assign(ring=RING_OUTER, hotspots=city_day["hotspots_250km"] - city_day["hotspots_100km"])
    return pd.concat([inner, outer], ignore_index=True)[["date_utc", "ring", "hotspots"]]


def season_ranking(city_day: pd.DataFrame) -> pd.DataFrame:
    ranking = city_day.groupby("city_name", as_index=False).agg(
        pm2_5_mean=("pm2_5_mean", "mean"),
        hotspots_250km=("hotspots_250km", "sum"),
    )
    return ranking.sort_values("pm2_5_mean", ascending=False, ignore_index=True)
