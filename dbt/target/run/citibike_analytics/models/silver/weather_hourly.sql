
      
        
        
        delete from "citibike"."silver"."weather_hourly" as DBT_INTERNAL_DEST
        where (observed_at) in (
            select distinct observed_at
            from "weather_hourly__dbt_tmp003303373192" as DBT_INTERNAL_SOURCE
        );

    

    insert into "citibike"."silver"."weather_hourly" ("observed_at", "temperature_2m", "relative_humidity_2m", "precipitation", "rain", "snowfall", "weather_code", "wind_speed_10m", "processed_at")
    (
        select "observed_at", "temperature_2m", "relative_humidity_2m", "precipitation", "rain", "snowfall", "weather_code", "wind_speed_10m", "processed_at"
        from "weather_hourly__dbt_tmp003303373192"
    )
  