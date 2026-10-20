-- The 100 km ring is inside the 250 km ring, so its count can never be larger.
select city_date_id, hotspots_100km, hotspots_250km
from {{ ref('city_day') }}
where hotspots_100km > hotspots_250km
