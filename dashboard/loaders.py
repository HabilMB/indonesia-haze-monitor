"""BigQuery loaders (marts only, read-only account), cached for an hour."""
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery
from google.oauth2 import service_account

from shape import combine_history

ARCHIVE_CSV = Path(__file__).resolve().parents[1] / "data" / "city_day_daily.csv"
TTL = 3600


class MissingConfig(Exception):
    pass


def _secret(name: str):
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        return None


def project_id() -> str:
    project = _secret("gcp_project_id") or os.environ.get("GCP_PROJECT_ID")
    if not project:
        raise MissingConfig("Set gcp_project_id in Streamlit secrets or the GCP_PROJECT_ID env var.")
    return project


@st.cache_resource
def client() -> bigquery.Client:
    info = _secret("gcp_service_account")
    try:
        if info:
            credentials = service_account.Credentials.from_service_account_info(dict(info))
            return bigquery.Client(project=project_id(), credentials=credentials)
        return bigquery.Client(project=project_id())
    except ValueError:
        raise MissingConfig("The [gcp_service_account] secret is malformed; paste the full service-account key fields.") from None
    except DefaultCredentialsError:
        raise MissingConfig(
            "No GCP credentials: add [gcp_service_account] to Streamlit secrets or set GOOGLE_APPLICATION_CREDENTIALS."
        ) from None


def _query(sql: str) -> pd.DataFrame:
    return client().query(sql).result(timeout=60).to_dataframe()


@st.cache_data(ttl=TTL)
def load_city_day() -> pd.DataFrame:
    bq = _query(f"select * from `{project_id()}.marts.city_day`")
    archive = pd.read_csv(ARCHIVE_CSV) if ARCHIVE_CSV.exists() else pd.DataFrame()
    return combine_history(bq, archive)


@st.cache_data(ttl=TTL)
def load_cities() -> pd.DataFrame:
    return _query(f"select * from `{project_id()}.marts.dim_city` order by city_name")


@st.cache_data(ttl=TTL)
def load_recent_hotspots() -> pd.DataFrame:
    return _query(f"""
        select latitude, longitude, acq_date, frp
        from `{project_id()}.marts.fact_hotspot`
        where confidence_level in ('nominal', 'high')
          and acq_date >= (select date_sub(max(acq_date), interval 2 day) from `{project_id()}.marts.fact_hotspot`)
    """)
