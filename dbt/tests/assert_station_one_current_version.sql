select station_id, count(*) as current_versions
from {{ source('silver_existing', 'dim_station') }}
where is_current
group by station_id
having count(*) > 1
