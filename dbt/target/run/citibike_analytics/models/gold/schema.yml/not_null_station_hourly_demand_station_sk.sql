
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select station_sk
from "citibike"."gold"."station_hourly_demand"
where station_sk is null



  
  
      
    ) dbt_internal_test