{{ config(
    partition_by={'field': 'date_utc', 'data_type': 'date', 'granularity': 'day'},
    cluster_by=['city_id']
) }}

select
    concat(city_id, '|', cast(date_utc as string)) as city_date_id,
    city_id,
    date_utc,
    avg(pm2_5) as pm2_5_mean,
    max(pm2_5) as pm2_5_max,
    avg(pm10) as pm10_mean,
    max(us_aqi) as us_aqi_max,
    countif(pm2_5 is not null) as hours_observed
from {{ ref('stg_open_meteo__air_quality_hourly') }}
group by city_id, date_utc
