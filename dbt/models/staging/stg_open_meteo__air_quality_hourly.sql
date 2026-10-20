select
    lower(replace(city, ' ', '_')) as city_id,
    city as city_name,
    time as measured_at,
    date as date_utc,
    pm2_5,
    pm10,
    us_aqi,
    ingested_at
from {{ source('raw', 'air_quality_hourly') }}
