{{ config(
    indexes=[
        {'columns': ['station_id', 'user_id'], 'unique': True},
        {'columns': ['user_id']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- dim_station_user 站点-运维人员桥表（一行 = 一个站点×一个责任人账号，每日全量）。
-- 源: guangdong_ods.sys_userstation（dbo.SYS_USERSTATION，约 3,659 行），
--     经 sys_user 解析姓名、sys_department 解析运维部门中文名。
-- 用途: 站点目录的"运维人员"维度（dim_station.manager_name 仅 alm_home 告警推送站，
--     约 63 站动态快照；本表提供全主网覆盖的站点→人员名册）。
-- 契约: sync/datasets/dim_station_user.yaml。
select distinct
    us.stationid::text         as station_id,
    u.userid::text             as user_id,
    u.username                 as user_name,
    nullif(trim(u.usercode), '') as user_code,
    u.departmentid::text       as department_id,
    d.departmentname           as department_name,
    u.status                   as user_status,
    now()::timestamp           as refreshed_at
from {{ source('guangdong_ods', 'sys_userstation') }} us
join {{ source('guangdong_ods', 'sys_user') }} u
       on u.userid = us.userid
left join {{ source('guangdong_ods', 'sys_department') }} d
       on d.departmentid = u.departmentid
