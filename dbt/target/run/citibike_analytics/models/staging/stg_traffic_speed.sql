
  create view "citibike"."staging"."stg_traffic_speed__dbt_tmp"
    
    
  as (
    select
    link_id,
    date_trunc('hour', data_as_of) as observed_hour,
    coalesce(nullif(btrim(borough), ''), 'UNKNOWN') as borough,
    speed,
    travel_time
from "citibike"."raw"."traffic_speed"
where data_as_of is not null
  );