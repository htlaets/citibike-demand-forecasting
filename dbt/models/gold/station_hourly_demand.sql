{{
  config(
    materialized='incremental',
    unique_key=['observed_hour', 'station_sk'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
  )
}}

with starts as (
    select
        date_trunc('hour', started_at) as observed_hour,
        start_station_sk as station_sk,
        count(*)::integer as rides_started
    from {{ source('silver_existing', 'fact_trip') }}
    where start_station_sk is not null
    {% if is_incremental() %}
      and started_at >= (
          select coalesce(max(observed_hour), '1900-01-01'::timestamptz) - interval '1 hour'
          from {{ this }}
      )
    {% endif %}
    group by 1, 2
),

ends as (
    select
        date_trunc('hour', ended_at) as observed_hour,
        end_station_sk as station_sk,
        count(*)::integer as rides_ended
    from {{ source('silver_existing', 'fact_trip') }}
    where end_station_sk is not null
    {% if is_incremental() %}
      and ended_at >= (
          select coalesce(max(observed_hour), '1900-01-01'::timestamptz) - interval '1 hour'
          from {{ this }}
      )
    {% endif %}
    group by 1, 2
),

demand as (
    select
        coalesce(s.observed_hour, e.observed_hour) as observed_hour,
        coalesce(s.station_sk, e.station_sk) as station_sk,
        coalesce(s.rides_started, 0)::integer as rides_started,
        coalesce(e.rides_ended, 0)::integer as rides_ended
    from starts s
    full outer join ends e
      on s.observed_hour = e.observed_hour
     and s.station_sk = e.station_sk
),

traffic_city as (
    select
        observed_hour,
        avg(avg_speed) as avg_traffic_speed,
        avg(avg_travel_time) as avg_travel_time
    from {{ ref('traffic_hourly') }}
    group by observed_hour
)

select
    d.observed_hour,
    d.station_sk,
    st.station_id,
    st.station_name,
    d.rides_started,
    d.rides_ended,
    w.temperature_2m,
    w.relative_humidity_2m,
    w.precipitation,
    w.snowfall,
    w.wind_speed_10m,
    t.avg_traffic_speed,
    t.avg_travel_time,
    extract(hour from d.observed_hour at time zone 'America/New_York')::smallint as hour_of_day,
    extract(dow from d.observed_hour at time zone 'America/New_York')::smallint as day_of_week,
    extract(month from d.observed_hour at time zone 'America/New_York')::smallint as month_num,
    (
      extract(isodow from d.observed_hour at time zone 'America/New_York') in (6, 7)
    ) as is_weekend,
    current_timestamp as refreshed_at
from demand d
join {{ source('silver_existing', 'dim_station') }} st
  on st.station_sk = d.station_sk
left join {{ ref('weather_hourly') }} w
  on w.observed_at = d.observed_hour
left join traffic_city t
  on t.observed_hour = d.observed_hour
where d.station_sk is not null
