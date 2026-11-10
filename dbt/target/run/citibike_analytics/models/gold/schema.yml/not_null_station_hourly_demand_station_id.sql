
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select station_id
from "citibike"."gold"."station_hourly_demand"
where station_id is null



  
  
      
    ) dbt_internal_test