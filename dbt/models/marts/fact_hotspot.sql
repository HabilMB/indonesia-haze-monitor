{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'acq_date', 'data_type': 'date', 'granularity': 'day', 'copy_partitions': true}
) }}

{#- The sandbox has no DML, so partitions are replaced with copy jobs instead of MERGE.
    Ingestion reloads whole partitions under one ingested_at, so a raw partition whose
    ingested_at differs from the copy in this table is stale here and is replaced in full.
    Comparing per partition (not against one global max) heals runs that failed part-way,
    overlapping runs and runner clock skew. -#}
select
    s.hotspot_id,
    s.acquired_at,
    s.acq_date,
    s.latitude,
    s.longitude,
    s.confidence_level,
    s.is_daytime,
    s.frp,
    s.brightness_ti4,
    s.brightness_ti5,
    s.satellite,
    s.ingested_at
from {{ ref('stg_firms__hotspots') }} as s
{% if is_incremental() %}
left join (
    select acq_date, max(ingested_at) as ingested_at
    from {{ this }}
    group by acq_date
) as t on s.acq_date = t.acq_date
where t.ingested_at is null or s.ingested_at != t.ingested_at
{% endif %}
