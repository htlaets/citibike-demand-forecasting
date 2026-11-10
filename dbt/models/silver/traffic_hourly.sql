{{
  config(
    materialized='incremental',
    unique_key=['observed_hour', 'borough'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
  )
}}

select
    observed_hour,
    borough,
    avg(speed) as avg_speed,
    avg(travel_time) as avg_travel_time,
    count(*)::integer as links_observed,
    current_timestamp as processed_at
from {{ ref('stg_traffic_speed') }}

{% if is_incremental() %}
where observed_hour >= (
    select coalesce(max(observed_hour), '1900-01-01'::timestamptz) - interval '1 hour'
    from {{ this }}
)
{% endif %}

group by observed_hour, borough
