select
    lower(replace(city, ' ', '_')) as city_id,
    city as city_name,
    province,
    latitude,
    longitude
from {{ ref('cities') }}
