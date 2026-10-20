select
    city_id,
    city_name,
    province,
    latitude,
    longitude
from {{ ref('stg_cities') }}
