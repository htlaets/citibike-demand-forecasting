
  create view "citibike"."staging"."stg_citibike_trips__dbt_tmp"
    
    
  as (
    select
    ride_id,
    rideable_type,
    started_at,
    ended_at,
    start_station_name,
    start_station_id,
    end_station_name,
    end_station_id,
    start_lat,
    start_lng,
    end_lat,
    end_lng,
    member_casual,
    extract(epoch from (ended_at - started_at))::integer as duration_seconds
from "citibike"."raw"."citibike_trips"
where started_at is not null
  and ended_at is not null
  and start_station_id is not null
  and btrim(start_station_id) <> ''
  and ended_at > started_at
  and ended_at - started_at <= interval '24 hours'
  );