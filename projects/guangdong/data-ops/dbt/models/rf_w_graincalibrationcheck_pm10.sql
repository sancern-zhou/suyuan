{{ config(
    indexes=[
        {'columns': ['graincalibrationcheckid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_w_graincalibrationcheck_pm10：契约透传层（源 dbo.RF_W_GrainCalibrationCheck_PM10，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_w_graincalibrationcheck_pm10.yaml；列名与 ODS 一致（源列名小写）。
select
    graincalibrationcheckid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    checkdate,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    processtype,
    snwd,
    snsd,
    czsj,
    kssj,
    jssj,
    bzmmodel,
    bjzccbh,
    cccj,
    xsjzq,
    xsjzh,
    edz1,
    edz2,
    bzz1,
    bzz2,
    d1wc1,
    d2wc2,
    old,
    new,
    pollutanttype,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_w_graincalibrationcheck_pm10') }}
