
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

select
    observed_at as unique_field,
    count(*) as n_records

from "citibike"."silver"."weather_hourly"
where observed_at is not null
group by observed_at
having count(*) > 1



  
  
      
    ) dbt_internal_test