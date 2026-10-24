{{ config(
    indexes=[
        {'columns': ['pwtaskid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- pw_task：契约透传层（源 dbo.PW_TASK，一行 = 一条原始记录）。
-- 契约: sync/datasets/pw_task.yaml；列名与 ODS 一致（源列名小写）。
select
    pwtaskid,
    rulename,
    ruletype,
    pwtasktime,
    finishpwtasktime,
    rulecycle,
    stationid,
    planworkid,
    sdtdate,
    edtdate,
    state,
    pwunitplanid,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'pw_task') }}
