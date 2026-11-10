
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  select station_id, count(*) as current_versions
from "citibike"."silver"."dim_station"
where is_current
group by station_id
having count(*) > 1
  
  
      
    ) dbt_internal_test