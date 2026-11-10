
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select rides_ended
from "citibike"."gold"."station_hourly_demand"
where rides_ended is null



  
  
      
    ) dbt_internal_test