
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  select *
from "citibike"."silver"."fact_trip"
where duration_seconds <= 0
   or duration_seconds > 86400
  
  
      
    ) dbt_internal_test