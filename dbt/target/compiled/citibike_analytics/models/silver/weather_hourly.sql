

select
    observed_at,
    temperature_2m,
    relative_humidity_2m,
    precipitation,
    rain,
    snowfall,
    weather_code,
    wind_speed_10m,
    current_timestamp as processed_at
from "citibike"."staging"."stg_weather_hourly"


where observed_at >= (
    select coalesce(max(observed_at), '1900-01-01'::timestamptz)
    from "citibike"."silver"."weather_hourly"
)
