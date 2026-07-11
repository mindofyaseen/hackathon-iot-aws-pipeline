with silver as (
    select * from {{ ref('stg_iot_events') }}
),

aggregated as (
    select
        device_id,
        date(event_ts)              as event_date,
        count(*)                    as event_count,
        round(avg(aqi), 2)          as avg_aqi,
        round(max(aqi), 2)          as max_aqi,
        round(min(aqi), 2)          as min_aqi,
        round(avg(temperature), 2)  as avg_temp,
        round(max(temperature), 2)  as max_temp,
        round(min(temperature), 2)  as min_temp,
        avg(lat)                    as avg_lat,
        avg(long)                   as avg_long,
        count(case when aqi_severity = 'unhealthy' then 1 end) as unhealthy_count,
        count(case when aqi_severity = 'moderate'  then 1 end) as moderate_count,
        min(event_ts)               as first_event_ts,
        max(event_ts)               as last_event_ts
    from silver
    group by device_id, date(event_ts)
)

select * from aggregated
