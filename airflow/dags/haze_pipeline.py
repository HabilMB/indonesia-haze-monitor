"""Daily haze pipeline: the same CLI entrypoints as .github/workflows/refresh.yml, orchestrated by Airflow."""
from datetime import datetime, timedelta, timezone

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

VENV_BIN = "/home/airflow/pipeline-venv/bin/"
DBT_ARGS = "--project-dir dbt --profiles-dir dbt"

DOC = """
Ingests the last 3 completed UTC days (FIRMS hotspots, Open-Meteo air quality) into BigQuery raw,
then runs `dbt build` and `dbt source freshness`.

**One production writer at a time.** The GitHub Actions cron (06:00 UTC) owns the live datasets, so
this DAG starts paused. Unpausing starts the latest 06:00 interval right away, so to run it once, unpause it away
from 06:00 UTC and pause it again afterwards; keep it unpaused only with that cron disabled.

The ingest window is relative to *now*, not to the run's logical date, so retrying or clearing an old
run re-pulls the current trailing 3 days (as a rerun of the GitHub workflow would).
"""

with DAG(
    dag_id="haze_pipeline",
    schedule="0 6 * * *",
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5), "execution_timeout": timedelta(minutes=20)},
    doc_md=DOC,
    tags=["haze"],
):
    common = {"cwd": "/opt/pipeline", "env": {"PYTHONPATH": "ingestion"}, "append_env": True}
    ingest = BashOperator(task_id="ingest", bash_command=VENV_BIN + "python -m haze_ingest", **common)
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{VENV_BIN}dbt build --exclude-resource-type unit_test {DBT_ARGS}",
        **common,
    )
    dbt_source_freshness = BashOperator(
        task_id="dbt_source_freshness", bash_command=f"{VENV_BIN}dbt source freshness {DBT_ARGS}", **common
    )

    ingest >> dbt_build >> dbt_source_freshness
