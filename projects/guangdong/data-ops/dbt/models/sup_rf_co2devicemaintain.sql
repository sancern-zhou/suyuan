{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
        {'columns': ['workingordercode']},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- sup_rf_co2devicemaintain：组分网/业务表同步透传层（源 dbo.sup_rf_co2devicemaintain；ops_audit 本地取数依赖）。
-- 列名与 ODS 一致（源列名小写）。由 sync/gen_passthrough_models.py 生成。
select
    id,
    workingordercode,
    stationid,
    stationcode,
    uniquecode,
    operationunitid,
    checkdate,
    deviceid,
    devicebrand,
    devicemodel,
    devicecode,
    prepareuserid,
    preparetime,
    reviewuserid,
    reviewtime,
    audituserid,
    audittime,
    processtype,
    createuserid,
    createtime,
    updateuserid,
    updatetime,
    remark,
    ruleitemtag,
    pollutanttype,
    detailid,
    datetime1,
    datetime2,
    datetime3,
    datetime4,
    insuserid1,
    insuserid2,
    insuserid3,
    insuserid4,
    _src_incremental,
    _sync_batch,
    _synced_at,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'sup_rf_co2devicemaintain') }}
