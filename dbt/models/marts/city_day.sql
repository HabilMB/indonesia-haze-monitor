{{ config(
    partition_by={'field': 'date_utc', 'data_type': 'date', 'granularity': 'day'},
    cluster_by=['city_id']
) }}

with near as (
    select
        c.city_id,
        h.acq_date as date_utc,
        countif(st_dwithin(st_geogpoint(c.longitude, c.latitude), st_geogpoint(h.longitude, h.latitude), 100000)) as hotspots_100km,
        count(*) as hotspots_250km
    from {{ ref('dim_city') }} as c
    inner join {{ ref('fact_hotspot') }} as h
        on st_dwithin(st_geogpoint(c.longitude, c.latitude), st_geogpoint(h.longitude, h.latitude), 250000)
    where h.confidence_level in ('nominal', 'high')
    group by c.city_id, h.acq_date
)

-- fact_air_quality_daily drives the grain, so quiet days stay as rows with zero counts.
select
    a.city_date_id,
    a.city_id,
    c.city_name,
    c.province,
    a.date_utc,
    a.pm2_5_mean,
    a.pm2_5_max,
    a.us_aqi_max,
    a.hours_observed,
    coalesce(n.hotspots_100km, 0) as hotspots_100km,
    coalesce(n.hotspots_250km, 0) as hotspots_250km
from {{ ref('fact_air_quality_daily') }} as a
inner join {{ ref('dim_city') }} as c on a.city_id = c.city_id
left join near as n on a.city_id = n.city_id and a.date_utc = n.date_utc
