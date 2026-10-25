{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- sup_rf_monthnephelometercheck：契约透传层（源 dbo.Sup_RF_MonthNepheloMeterCheck，每日全量；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/sup_rf_monthnephelometercheck.yaml；列名与 ODS 一致（源列名小写）。
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
    yqzt,
    yqyxcs,
    yqyxsz,
    cyfjyzqk,
    xjbz2,
    xjbz3,
    xjbz4,
    hwcytqj,
    clsqsqj,
    remark1,
    remark2,
    ruleitemtag,
    pollutanttype,
    detailid,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'sup_rf_monthnephelometercheck') }}
