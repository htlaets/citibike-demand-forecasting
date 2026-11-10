
  create view "citibike"."staging"."stg_weather_hourly__dbt_tmp"
    
    
  as (
    select
    date_trunc('hour', observed_at) as observed_at,
    temperature_2m,
    relative_humidity_2m,
    precipitation,
    rain,
    snowfall,
    weather_code,
    wind_speed_10m
from "citibike"."raw"."weather_hourly"
where observed_at is not null
  );