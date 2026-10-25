{{ config(
    indexes=[
        {'columns': ['rfwlongopticalpathid'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_w_longopticalpath：契约透传层（源 dbo.RF_W_LONGOPTICALPATH，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_w_longopticalpath.yaml；列名与 ODS 一致（源列名小写）。
select
    rfwlongopticalpathid,
    workingordercode,
    stationid,
    operationsunitid,
    areaid,
    calibrationdate,
    devicemodel,
    devicecode,
    checkdate,
    lightintensityvalue,
    lightintensitysituation,
    spectrumcheck,
    spectrumsituation,
    gratingcheck,
    gratingsituation,
    starttimeso2,
    endtimeso2,
    displayvalueso2,
    calibrationvalueso2,
    starttimeno2,
    endtimeno2,
    displayvalueno2,
    calibrationvalueno2,
    starttimeo3,
    endtimeo3,
    displayvalueo3,
    calibrationvalueo3,
    remark,
    prepareruserid,
    reviewuserid,
    auditoruserid,
    preparerdate,
    reviewdate,
    auditordate,
    createdate,
    defaultvalue,
    processtype,
    islddevice,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_w_longopticalpath') }}
