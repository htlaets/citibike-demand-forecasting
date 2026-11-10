select observed_hour, station_sk, count(*) as row_count
from "citibike"."gold"."station_hourly_demand"
group by observed_hour, station_sk
having count(*) > 1