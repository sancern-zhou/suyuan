{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- sup_mtc_taskitem：契约透传层（源 dbo.Sup_Mtc_TaskItem，一行 = 一条原始记录）。
-- 契约: sync/datasets/sup_mtc_taskitem.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    workingordercode,
    deviceid,
    ruletype,
    ruleitemtag,
    pollutanttype,
    finishtime,
    planfinishtime,
    status,
    createuserid,
    createtime,
    processtype,
    detailid,
    tablename,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'sup_mtc_taskitem') }}
