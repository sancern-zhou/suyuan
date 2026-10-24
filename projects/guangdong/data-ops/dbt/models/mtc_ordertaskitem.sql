{{ config(
    indexes=[
        {'columns': ['ordertaskitemid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- mtc_ordertaskitem：契约透传层（源 dbo.MTC_ORDERTASKITEM，一行 = 一条原始记录）。
-- 契约: sync/datasets/mtc_ordertaskitem.yaml；列名与 ODS 一致（源列名小写）。
select
    ordertaskitemid,
    workingordercode,
    ruleitemtag,
    pollutanttype,
    checkprocessstatus,
    sdtdate,
    edtdate,
    planfinishtime,
    processtype,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'mtc_ordertaskitem') }}
