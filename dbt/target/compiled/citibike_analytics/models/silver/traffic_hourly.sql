

select
    observed_hour,
    borough,
    avg(speed) as avg_speed,
    avg(travel_time) as avg_travel_time,
    count(*)::integer as links_observed,
    current_timestamp as processed_at
from "citibike"."staging"."stg_traffic_speed"


where observed_hour >= (
    select coalesce(max(observed_hour), '1900-01-01'::timestamptz) - interval '1 hour'
    from "citibike"."silver"."traffic_hourly"
)


group by observed_hour, borough