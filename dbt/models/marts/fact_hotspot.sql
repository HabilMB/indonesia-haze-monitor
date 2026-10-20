{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'acq_date', 'data_type': 'date', 'granularity': 'day', 'copy_partitions': true}
) }}

{#- The sandbox has no DML, so partitions are replaced with copy jobs instead of MERGE.
    Ingestion reloads whole partitions under one ingested_at, so filtering on ingested_at
    picks up every reloaded partition in full, including backfills of old dates. -#}
select
    hotspot_id,
    acquired_at,
    acq_date,
    latitude,
    longitude,
    confidence_level,
    is_daytime,
    frp,
    brightness_ti4,
    brightness_ti5,
    satellite,
    ingested_at
from {{ ref('stg_firms__hotspots') }}
{% if is_incremental() %}
where ingested_at > (select coalesce(max(ingested_at), timestamp('1970-01-01')) from {{ this }})
{% endif %}
