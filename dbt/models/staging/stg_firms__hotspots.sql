with hotspots as (
    select
        to_hex(sha256(concat(
            satellite, '|', cast(latitude as string), '|', cast(longitude as string), '|',
            cast(acq_date as string), '|', acq_time
        ))) as hotspot_id,
        timestamp(datetime(acq_date, parse_time('%H%M', acq_time))) as acquired_at,
        acq_date,
        latitude,
        longitude,
        case confidence
            when 'l' then 'low'
            when 'n' then 'nominal'
            when 'h' then 'high'
        end as confidence_level,
        daynight = 'D' as is_daytime,
        frp,
        bright_ti4 as brightness_ti4,
        bright_ti5 as brightness_ti5,
        satellite,
        ingested_at
    from {{ source('raw', 'firms_hotspots') }}
)

select *
from hotspots
-- FIRMS can re-serve the same detection; one duplicate must not fail `unique` and halt the pipeline.
where true
qualify row_number() over (partition by hotspot_id order by ingested_at desc) = 1
