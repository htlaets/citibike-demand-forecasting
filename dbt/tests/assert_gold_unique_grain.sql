select observed_hour, station_sk, count(*) as row_count
from {{ ref('station_hourly_demand') }}
group by observed_hour, station_sk
having count(*) > 1
