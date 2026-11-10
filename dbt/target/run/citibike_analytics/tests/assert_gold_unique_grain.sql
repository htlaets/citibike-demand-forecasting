
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  select observed_hour, station_sk, count(*) as row_count
from "citibike"."gold"."station_hourly_demand"
group by observed_hour, station_sk
having count(*) > 1
  
  
      
    ) dbt_internal_test