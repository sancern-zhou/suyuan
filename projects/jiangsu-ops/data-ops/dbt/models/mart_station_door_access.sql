{{ config(
    materialized='table',
    tags=['daily'],
    indexes=[
        {'columns': ['station_code', 'event_time']},
        {'columns': ['event_type_cn']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '站点门禁出入事件(海康ACS, 每日02:30增量, 3天重叠窗口)。一行=一条开门/刷卡事件; 源为平台API stationintegrate/HK(GetACSDoorRecordsAsync), 经 sync_door_access.py 落 jiangsu_ods.acs_door_records; event_type_cn: successCard=合法卡比对通过, infoOpenDoorByButton=按钮开门; cert_no_masked 为脱敏证件号, 原文在 ODS 层; inAndOutType 进/出口径待平台确认(1 见于刷卡, -1 见于按钮开门)。'",
    ],
) }}

-- mart_station_door_access: 站点门禁出入事件(海康门禁)
-- 源: 平台 API stationintegrate/HK/GetACSDoorRecordsAsync → sync_door_access.py → jiangsu_ods.acs_door_records
-- 用途: 人员进站核验(签到之外的独立进站证据)、运维到岗分析。
-- 边界: 门禁是离散开关门/刷卡事件, 不是连续轨迹; 卡可能共用, 不能据此认定实际进站人员。
-- station_code 由 devName 经 dim_station.station_name 精确匹配回填, 匹配不上为空(dev_name 保留原文)。
with base as (
    select
        event_id, station_code, dev_name, door_name, event_time, receive_time,
        event_name, event_type, in_and_out_type, person_id, person_name,
        card_no, org_name, cert_no, reader_dev_name
    from {{ source('jiangsu_ods', 'acs_door_records') }}
)
select
    b.event_id,
    b.station_code,
    ds.station_name,
    ds.city_code,
    ds.city_name,
    b.dev_name,
    b.door_name,
    b.event_time,
    b.receive_time,
    b.event_name,
    case b.event_name
        when 'acs.acs.eventType.successCard' then '合法卡比对通过'
        when 'acs.acs.eventType.infoOpenDoorByButton' then '按钮开门'
        else coalesce(nullif(split_part(b.event_name, '.', -1), ''), b.event_name)
    end                                          as event_type_cn,
    b.event_type,
    b.in_and_out_type,
    b.person_id,
    b.person_name,
    b.card_no,
    b.org_name,
    case when b.cert_no is null or length(b.cert_no) < 11 then null
         else concat(left(b.cert_no, 6), '********', right(b.cert_no, 4))
    end                                          as cert_no_masked,
    b.reader_dev_name,
    now()::timestamp                             as synced_at
from base b
left join {{ ref('dim_station') }} ds
       on ds.station_code = b.station_code
