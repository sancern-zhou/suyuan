{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['station_code']},
        {'columns': ['start_time']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '停电单宽表(每日刷新)。stop_type 语义待业务确认,列名已带(待确认)标记;duration_hours=结束-开始。用于停电时段与离线/断数告警的合规核验。'",
    ],
) }}

-- mart_blackout_analysis: 停电单宽表
-- 一行 = 一张停电报备单(mtc_BlackOut, 全量 65 行,每日刷新)。
-- 口径注意: stop_type 0/1 语义待业务确认(按分布猜测 0=计划停电/1=故障停电)。
-- 场景: 高值时段停电合规核验(停电时段 vs 离线/断数告警)。
select
    b.id                     as id,
    b.stationcode            as station_code,
    ds.station_name          as station_name,
    ds.city_code             as city_code,
    ds.city_name             as city_name,
    b.stoptype               as stop_type,
    case b.stoptype when '0' then '计划停电(待确认)' when '1' then '故障停电(待确认)' else b.stoptype end
                             as stop_type_cn,
    b.ordertype_text         as order_type_text,
    b.sdttime                as start_time,
    b.edttime                as end_time,
    extract(epoch from (b.edttime - b.sdttime)) / 3600.0 as duration_hours,
    b.iscancel               as is_cancel,
    b.abnormal               as abnormal,
    b.remark                 as remark,
    b.createtime             as source_create_time,
    b.updatetime             as source_update_time,
    now()::timestamp         as synced_at
from {{ source('jiangsu_ods', 'mtc_blackout') }} b
left join {{ ref('dim_station') }} ds
       on ds.station_code = b.stationcode
