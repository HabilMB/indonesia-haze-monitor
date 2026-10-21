from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag

DAGS = Path(__file__).resolve().parents[1] / "dags"
VENV_BIN = "/home/airflow/pipeline-venv/bin/"


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(dag_folder=DAGS)


@pytest.fixture(scope="module")
def dag(dagbag):
    return dagbag.dags["haze_pipeline"]


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}
    assert "haze_pipeline" in dagbag.dag_ids


def test_task_order(dag):
    assert dag.get_task("ingest").downstream_task_ids == {"dbt_build"}
    assert dag.get_task("dbt_build").downstream_task_ids == {"dbt_source_freshness"}
    assert dag.get_task("dbt_source_freshness").downstream_task_ids == set()


def test_commands_match_refresh_workflow(dag):
    expected = {
        "ingest": VENV_BIN + "python -m haze_ingest",
        "dbt_build": VENV_BIN + "dbt build --exclude-resource-type unit_test --project-dir dbt --profiles-dir dbt",
        "dbt_source_freshness": VENV_BIN + "dbt source freshness --project-dir dbt --profiles-dir dbt",
    }
    for task_id, command in expected.items():
        task = dag.get_task(task_id)
        assert task.bash_command.strip() == command
        assert task.cwd == "/opt/pipeline"
        assert task.env == {"PYTHONPATH": "ingestion"}
        assert task.append_env is True


def test_schedule_and_safety(dag):
    assert dag.schedule == "0 6 * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    for task in dag.tasks:
        assert task.retries >= 2
        assert task.execution_timeout is not None
