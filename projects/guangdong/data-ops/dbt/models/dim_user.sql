{{ config(
    indexes=[
        {'columns': ['user_id'], 'unique': True},
        {'columns': ['department_id']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- dim_user 运维用户维度（一行 = 一个平台账号，约 1,036 个，每日全量）。
-- 源: guangdong_ods.sys_user（dbo.SYS_USER；敏感列 PASSWORD/IDCARDNO/CELLPHONE/EMAIL/WORKCARDNO
--     在同步层即被排除，不入本地库）。
-- 用途: 工单/任务项的 create_user_id/finish_user_id/process_user_id 解析为中文名。
-- 契约: sync/datasets/dim_user.yaml。
select
    u.userid::text             as user_id,
    u.username                 as user_name,
    nullif(trim(u.usercode), '') as user_code,
    u.loginid                  as login_id,
    u.departmentid::text       as department_id,
    d.departmentname           as department_name,
    u.status                   as status,
    u.rank                     as user_rank,
    u.maintenanceunitid::text  as maintenance_unit_id,
    u.usertype                 as user_type,
    u.regionid::text           as region_id,
    now()::timestamp           as refreshed_at
from {{ source('guangdong_ods', 'sys_user') }} u
left join {{ source('guangdong_ods', 'sys_department') }} d
       on d.departmentid = u.departmentid
