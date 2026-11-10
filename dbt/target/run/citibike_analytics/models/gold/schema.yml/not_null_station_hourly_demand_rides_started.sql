
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select rides_started
from "citibike"."gold"."station_hourly_demand"
where rides_started is null



  
  
      
    ) dbt_internal_test