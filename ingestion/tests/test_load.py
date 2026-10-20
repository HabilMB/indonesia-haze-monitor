from datetime import date

import pytest
from google.cloud import bigquery

from haze_ingest.load import ensure_table, load_partitions

T = "proj.raw.firms_hotspots"
SCHEMA = [bigquery.SchemaField("acq_date", "DATE"), bigquery.SchemaField("x", "INT64")]


def test_loads_each_date_into_its_partition_with_truncate(fake):
    rows = [{"acq_date": "2026-10-17", "x": 1}, {"acq_date": "2026-10-18", "x": 2}, {"acq_date": "2026-10-18", "x": 3}]
    counts = load_partitions(fake, T, SCHEMA, rows, "acq_date", [date(2026, 10, 17), date(2026, 10, 18)])
    assert counts == {date(2026, 10, 17): 1, date(2026, 10, 18): 2}
    assert [c.destination for c in fake.loads] == [f"{T}$20261017", f"{T}$20261018"]
    assert all(c.job_config.write_disposition == "WRITE_TRUNCATE" for c in fake.loads)
    assert all(c.job_config.source_format == "NEWLINE_DELIMITED_JSON" for c in fake.loads)
    assert all(c.timeout is not None for c in fake.loads)


def test_empty_date_deletes_partition(fake):
    counts = load_partitions(fake, T, SCHEMA, [], "acq_date", [date(2026, 10, 19)])
    assert counts == {date(2026, 10, 19): 0}
    assert fake.deleted == [(f"{T}$20261019", True)]
    assert fake.loads == []


def test_rows_outside_window_raise(fake):
    with pytest.raises(ValueError, match="2026-10-20"):
        load_partitions(fake, T, SCHEMA, [{"acq_date": "2026-10-20"}], "acq_date", [date(2026, 10, 19)])
    assert fake.loads == [] and fake.deleted == []


def test_ensure_table_partitions_and_clusters(fake):
    ensure_table(fake, "proj.raw.air_quality_hourly", SCHEMA, "date", ["city"])
    t = fake.created[0]
    assert t.time_partitioning.field == "date" and t.time_partitioning.type_ == "DAY"
    assert t.clustering_fields == ["city"] and fake.exists_ok is True
