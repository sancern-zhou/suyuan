{{ config(
    indexes=[
        {'columns': ['station_id'], 'unique': True},
        {'columns': ['station_code']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- dim_station 站点目录一致性维度（一行 = 一个站点，约 332 站全量）。
-- 源: guangdong_ods.base_station（dbo.base_station，每日全量）。
-- 契约: sync/datasets/dim_station.yaml（station_id 输出为文本形式，工单表直接等值关联）。
-- 城市维度增强（2026-10-25）: 源库无区域字典，城市码/城市名/站点类型中文名经
-- guangdong_ods.alm_home（站点告警态势快照，每日刷新）补充——alm_home 一行一站，
-- RegionId=城市行政区码(440100)、RegionName=城市名、TypeName=站点类型中文名(省控等)、
-- UserName=运维管理人。alm_home 无行的站点城市为 NULL。
select
    b.stationid::text          as station_id,
    trim(b.code)               as station_code,
    trim(b.name)               as station_name,
    b.regionid::text           as region_id,
    h.regionid                 as city_code,
    h.regionname               as city_name,
    h.typename                 as station_type_name,
    h.username                 as manager_name,
    b.longitude,
    b.latitude,
    b.address,
    b.ddstationtype::smallint  as station_type,
    b.status::smallint         as status,
    nullif(trim(b.uniquecode), '') as unique_code,
    b.monitorip                as monitor_ip,
    b.mappingstationid::text   as mapping_station_id,
    nullif(trim(b.operationtype), '') as operation_type,
    b.description,
    b.createtime               as create_time,
    now()::timestamp           as refreshed_at
from {{ source('guangdong_ods', 'base_station') }} b
left join {{ source('guangdong_ods', 'alm_home') }} h
       on h.stationid = b.stationid::text
