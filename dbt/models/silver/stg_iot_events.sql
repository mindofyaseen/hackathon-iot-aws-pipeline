with raw as (
    select
        RECORD_CONTENT:after as after,
        INSERTED_AT
    from {{ source('raw', 'IOT_EVENTS') }}
    where RECORD_CONTENT:op::string in ('r', 'c', 'u')
      and RECORD_CONTENT:after is not null
),

parsed as (
    select
        after:device_id::varchar                          as device_id,
        after:lat::float                                  as lat,
        after:long::float                                 as long,
        after:temperature::float                          as temperature,
        after:aqi::float                                  as aqi,
        to_timestamp_ntz(after:ts::varchar)               as event_ts,
        INSERTED_AT                                       as inserted_at
    from raw
    where after:device_id is not null
      and after:ts is not null
),

tagged as (
    select
        *,
        case
            when aqi > 150 then 'unhealthy'
            when aqi > 100 then 'moderate'
            else 'good'
        end as aqi_severity
    from parsed
)

select * from tagged
