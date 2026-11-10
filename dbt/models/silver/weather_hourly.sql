{{
  config(
    materialized='incremental',
    unique_key='observed_at',
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
  )
}}

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
from {{ ref('stg_weather_hourly') }}

{% if is_incremental() %}
where observed_at >= (
    select coalesce(max(observed_at), '1900-01-01'::timestamptz)
    from {{ this }}
)
{% endif %}
