
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select observed_hour
from "citibike"."silver"."traffic_hourly"
where observed_hour is null



  
  
      
    ) dbt_internal_test