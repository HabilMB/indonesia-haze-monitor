from collections import defaultdict
from datetime import date
from typing import Iterable

from google.cloud import bigquery

JOB_TIMEOUT = 300


def ensure_table(
    client: bigquery.Client,
    table_id: str,
    schema: list[bigquery.SchemaField],
    partition_field: str,
    clustering_fields: list[str] | None = None,
) -> None:
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY, field=partition_field)
    table.clustering_fields = clustering_fields
    client.create_table(table, exists_ok=True)


def load_partitions(
    client: bigquery.Client,
    table_id: str,
    schema: list[bigquery.SchemaField],
    rows: list[dict],
    partition_field: str,
    dates: Iterable[date],
) -> dict[date, int]:
    # Sandbox has no DML: each date is replaced by a WRITE_TRUNCATE load into its partition,
    # and a date with no rows has its partition deleted so stale rows can't survive a re-pull.
    dates = list(dates)
    by_date = defaultdict(list)
    for row in rows:
        by_date[date.fromisoformat(row[partition_field])].append(row)
    outside = sorted(set(by_date) - set(dates))
    if outside:
        raise ValueError(f"{table_id}: rows for dates outside the load window: {', '.join(map(str, outside))}")

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    counts = {}
    for day in dates:
        partition = f"{table_id}${day:%Y%m%d}"
        day_rows = by_date.get(day, [])
        if day_rows:
            client.load_table_from_json(day_rows, partition, job_config=job_config).result(timeout=JOB_TIMEOUT)
        else:
            client.delete_table(partition, not_found_ok=True)
        counts[day] = len(day_rows)
    return counts
