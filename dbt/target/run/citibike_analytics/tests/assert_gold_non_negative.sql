
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  select *
from "citibike"."gold"."station_hourly_demand"
where rides_started < 0
   or rides_ended < 0
  
  
      
    ) dbt_internal_test