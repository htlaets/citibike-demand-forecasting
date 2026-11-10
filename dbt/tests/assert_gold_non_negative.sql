select *
from {{ ref('station_hourly_demand') }}
where rides_started < 0
   or rides_ended < 0
