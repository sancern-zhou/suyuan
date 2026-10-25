{{ config(
    indexes=[
        {'columns': ['user_id']},
        {'columns': ['department_name']},
        {'columns': ['has_work_license']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
        "COMMENT ON TABLE {{ this }} IS '运维人员维度表(每日全量,源自 jiangsu_ods.opa_user_info)。一行=一名人员(user_id);has_work_license 为平台持证标记,work_number 为证书编号(源表无证书类型/发证机构/有效期);cert_shared_count=同证号人数(>1 表示证号复用);group_names/station_count 为班组责任口径(bsd_usergroup_user→bsd_usergroup→bsd_usergroup_station)。'",
    ],
) }}

-- dim_person: 运维人员维度表（来自 jiangsu_ods.opa_user_info，每日全量）。
-- 用途：人员名册、运维单位归属、持证情况核查、班组责任站点范围。
-- 口径说明：
--   1) 持证只有"是否持证 + 证号"两列，源表无证书类型/发证机构/有效期，
--      不能回答"证书是否快到期"。
--   2) station_count 是"所在班组的责任站点数"，不是个人直接负责站点数。
--   3) cert_shared_count 由证号分组计数得出，用于识别证号被多人共用。
with person as (
    select * from {{ source('jiangsu_ods', 'opa_user_info') }}
),

user_group as (
    select
        u.userid,
        count(distinct g.groupcode)                        as group_count,
        string_agg(distinct g.groupname, '、' order by g.groupname)        as group_names,
        string_agg(distinct nullif(btrim(g.institutionname), ''), '、'
                   order by nullif(btrim(g.institutionname), ''))          as institution_names
    from {{ source('jiangsu_ods', 'bsd_usergroup_user') }} u
    join {{ source('jiangsu_ods', 'bsd_usergroup') }} g
      on g.groupcode = u.groupcode
    group by u.userid
),

-- bsd_usergroup_station.usergroup_guid 实际存的是班组编码(groupcode)，不是 GUID
group_station as (
    select
        u.userid,
        count(distinct s.stationcode) as station_count
    from {{ source('jiangsu_ods', 'bsd_usergroup_user') }} u
    join {{ source('jiangsu_ods', 'bsd_usergroup_station') }} s
      on s.usergroup_guid = u.groupcode
    group by u.userid
),

cert_usage as (
    select
        nullif(btrim(worknumber), '') as work_number,
        count(*)                      as cert_shared_count
    from {{ source('jiangsu_ods', 'opa_user_info') }}
    where nullif(btrim(worknumber), '') is not null
    group by 1
)

select
    p.id,
    p.userid                           as user_id,
    p.username                         as user_name,
    p.position,
    p.title,
    p.hasworklicense                   as has_work_license,
    nullif(btrim(p.worknumber), '')    as work_number,
    p.departmentcode                   as department_code,
    p.departmentname                   as department_name,
    p.achievement,
    p.achievementposition              as achievement_position,
    p.remark,
    coalesce(ug.group_count, 0)        as group_count,
    ug.group_names,
    ug.institution_names,
    coalesce(gs.station_count, 0)      as station_count,
    coalesce(cu.cert_shared_count, 0)  as cert_shared_count,
    p.createtime                       as create_time,
    p.updatetime                       as update_time,
    now()::timestamp                   as synced_at
from person p
left join user_group ug
       on ug.userid = p.userid
left join group_station gs
       on gs.userid = p.userid
left join cert_usage cu
       on cu.work_number = nullif(btrim(p.worknumber), '')
