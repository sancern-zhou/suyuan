{{ config(
    indexes=[
        {'columns': ['pwtaskitemid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- pw_taskitem：契约透传层（源 dbo.PW_TASKITEM，一行 = 一条原始记录）。
-- 契约: sync/datasets/pw_taskitem.yaml；列名与 ODS 一致（源列名小写）。
select
    pwtaskitemid,
    pwtaskid,
    ruleitemtag,
    pollutanttype,
    finishworkordercode,
    finishuserid,
    finishdatetime,
    taskuserid,
    sdtdate,
    edtdate,
    state,
    createuserid,
    createtime,
    basedate,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'pw_taskitem') }}
