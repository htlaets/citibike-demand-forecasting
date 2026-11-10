select station_id, count(*) as current_versions
from "citibike"."silver"."dim_station"
where is_current
group by station_id
having count(*) > 1