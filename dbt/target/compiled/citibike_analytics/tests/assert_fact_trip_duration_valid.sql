select *
from "citibike"."silver"."fact_trip"
where duration_seconds <= 0
   or duration_seconds > 86400