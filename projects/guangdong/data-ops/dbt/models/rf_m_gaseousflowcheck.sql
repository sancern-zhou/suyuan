{{ config(
    indexes=[
        {'columns': ['rfmgaseousflowcheckid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_m_gaseousflowcheck：契约透传层（源 dbo.RF_M_GASEOUSFLOWCHECK，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_m_gaseousflowcheck.yaml；列名与 ODS 一致（源列名小写）。
select
    rfmgaseousflowcheckid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    checkdate2,
    devicemodelso2,
    flowrangso2,
    displayvalueso2,
    measuredvalueso2,
    measurederrorso2,
    situationso2,
    devicemodelno2,
    flowrangno2,
    displayvalueno2,
    measuredvalueno2,
    measurederrorno2,
    situationno2,
    devicemodelco,
    flowrangco,
    displayvalueco,
    measuredvalueco,
    measurederrorco,
    situationco,
    devicemodelo3,
    flowrango3,
    displayvalueo3,
    measuredvalueo3,
    measurederroro3,
    situationo3,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    processtype,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_m_gaseousflowcheck') }}
