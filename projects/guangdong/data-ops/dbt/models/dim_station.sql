{{ config(
    indexes=[
        {'columns': ['station_id'], 'unique': True},
        {'columns': ['station_code']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- dim_station 站点目录一致性维度（一行 = 一个站点，432 站 = 主网 332 + 组分网 100）。
-- 主网源: guangdong_ods.base_station（每日全量）；组分网源: v_supcityandregionanddepartment
-- （每日全量，ID 空间 1~102 与主网 1000+ 不重叠）。
-- 城市维度（2026-10-25 二期）: 两个 city 视图全站覆盖；DDStationType 按字典映射中文名。
-- manager_name 来自 alm_home（仅告警推送站点，约 63 站，供参考）。
-- 契约: sync/datasets/dim_station.yaml（station_id 输出为文本形式）。
select
    b.stationid::text          as station_id,
    trim(b.code)               as station_code,
    trim(b.name)               as station_name,
    b.regionid::text           as region_id,
    v.regionid                 as city_code,
    v.regionname               as city_name,
    case v.ddstationtype::numeric
        when 1 then '国控站'
        when 2 then '省控站'
        when 3 then '市控站'
        when 4 then '区域站'
        when 5 then '乡镇站'
        when 6 then '省建站'
        when 7 then '省乡镇站'
        when 9 then 'VOC站'
        else '未知(' || coalesce(v.ddstationtype::text, 'null') || ')'
    end                        as station_type_name,
    v.departmentid              as operation_unit_id,
    v.operationdepatment       as operation_unit_name,
    v.departmentname           as department_name,
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
left join {{ source('guangdong_ods', 'v_cityandregionanddepartment') }} v
       on v.stationid2 = b.stationid
left join {{ source('guangdong_ods', 'alm_home') }} h
       on h.stationid = b.stationid::text

union all

select
    sup.stationid2::text       as station_id,
    trim(sup.stationcode)      as station_code,
    trim(sup.stationname)      as station_name,
    null::text                 as region_id,
    sup.regionid               as city_code,
    sup.regionname             as city_name,
    '组分站'                   as station_type_name,
    null::text                 as operation_unit_id,
    sup.operationdepatment     as operation_unit_name,
    null::text                 as department_name,
    null::text                 as manager_name,
    null::text                 as longitude,
    null::text                 as latitude,
    null::text                 as address,
    null::smallint             as station_type,
    sup.status::smallint       as status,
    nullif(trim(sup.uniquecode), '') as unique_code,
    null::text                 as monitor_ip,
    null::text                 as mapping_station_id,
    '组分网'                   as operation_type,
    null::text                 as description,
    null::timestamp            as create_time,
    now()::timestamp           as refreshed_at
from {{ source('guangdong_ods', 'v_supcityandregionanddepartment') }} sup
