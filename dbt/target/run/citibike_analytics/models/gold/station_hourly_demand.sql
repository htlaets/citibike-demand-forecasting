
      
        delete from "citibike"."gold"."station_hourly_demand" as DBT_INTERNAL_DEST
        where (observed_hour, station_sk) in (
            select distinct observed_hour, station_sk
            from "station_hourly_demand__dbt_tmp003303823662" as DBT_INTERNAL_SOURCE
        );

    

    insert into "citibike"."gold"."station_hourly_demand" ("observed_hour", "station_sk", "station_id", "station_name", "rides_started", "rides_ended", "temperature_2m", "relative_humidity_2m", "precipitation", "snowfall", "wind_speed_10m", "avg_traffic_speed", "avg_travel_time", "hour_of_day", "day_of_week", "month_num", "is_weekend", "refreshed_at")
    (
        select "observed_hour", "station_sk", "station_id", "station_name", "rides_started", "rides_ended", "temperature_2m", "relative_humidity_2m", "precipitation", "snowfall", "wind_speed_10m", "avg_traffic_speed", "avg_travel_time", "hour_of_day", "day_of_week", "month_num", "is_weekend", "refreshed_at"
        from "station_hourly_demand__dbt_tmp003303823662"
    )
  