{{ config(
    indexes=[
        {'columns': ['id'], 'unique': True},
    ],
    post_hook=[
        "GRANT SELECT ON {{ this }} TO agent_reader",
    ],
) }}

-- rf_w_graincalibrationcheckattach：契约透传层（源 dbo.RF_W_GrainCalibrationCheckAttach，全量同步；ops_audit 本地取数依赖）。
-- 契约: sync/datasets/rf_w_graincalibrationcheckattach.yaml；列名与 ODS 一致（源列名小写）。
select
    id,
    workingordercode,
    lljxh,
    lljccbh,
    pollutant,
    sycjcz,
    xycjcz,
    xdwc,
    formtype,
    now()::timestamp         as refreshed_at
from {{ source('guangdong_ods', 'rf_w_graincalibrationcheckattach') }}
