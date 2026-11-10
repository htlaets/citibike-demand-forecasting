
      
        delete from "citibike"."silver"."traffic_hourly" as DBT_INTERNAL_DEST
        where (observed_hour, borough) in (
            select distinct observed_hour, borough
            from "traffic_hourly__dbt_tmp003303391123" as DBT_INTERNAL_SOURCE
        );

    

    insert into "citibike"."silver"."traffic_hourly" ("observed_hour", "borough", "avg_speed", "avg_travel_time", "links_observed", "processed_at")
    (
        select "observed_hour", "borough", "avg_speed", "avg_travel_time", "links_observed", "processed_at"
        from "traffic_hourly__dbt_tmp003303391123"
    )
  