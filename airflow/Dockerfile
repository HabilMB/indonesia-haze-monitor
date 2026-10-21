FROM apache/airflow:3.3.2-python3.12

# The pipeline gets its own venv: Airflow's pinned constraints and dbt's dependencies stay independent.
COPY ingestion/requirements.txt /tmp/requirements/ingestion.txt
COPY dbt/requirements.txt /tmp/requirements/dbt.txt
RUN python -m venv /home/airflow/pipeline-venv \
    && /home/airflow/pipeline-venv/bin/pip install --no-cache-dir \
        -r /tmp/requirements/ingestion.txt -r /tmp/requirements/dbt.txt
