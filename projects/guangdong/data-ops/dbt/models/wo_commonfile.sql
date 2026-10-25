{{ config(
    indexes=[
        {'columns': ['wcfid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- wo_commonfile 工单附件主表透传（源 dbo.WO_COMMONFILE，CREATEDATE 今年窗口增量）。
-- 契约: sync/datasets/wo_commonfile.yaml；ops_audit 本地取数依赖本表。
select
    wcfid,
    refid,
    functioncode,
    typecode,
    filename,
    filepath,
    remark,
    createuserid,
    createdate,
    updateuserid,
    updatedate,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'wo_commonfile') }}
