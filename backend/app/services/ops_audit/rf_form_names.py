"""Display names for RF forms used by operations audit reports."""

from __future__ import annotations


RF_FORM_NAMES: dict[str, str] = {
    "RF_W_GASEOUSCHECK_CO": "一氧化碳（CO）分析仪运行状况检查记录表（每周）",
    "RF_W_GASEOUSCHECK_NOX": "氮氧化物（NOx）分析仪运行状况检查记录表（每周）",
    "RF_W_GASEOUSCHECK_O3": "臭氧（O3）分析仪运行状况检查记录表（每周）",
    "RF_W_GASEOUSCHECK_SO2": "二氧化硫（SO2）分析仪运行状况检查记录表（每周）",
    "RF_W_GrainCalibrationCheck_PM10": "PM10颗粒物校准检查记录表（每周）",
    "RF_W_GrainCalibrationCheck_PM25": "PM2.5颗粒物校准检查记录表（每周）",
    "RF_W_GrainCalibrationCheckAttach": "颗粒物校准检查附件表（每周）",
    "RF_W_INSPECTION": "巡检记录表（每周）",
    "RF_W_INSPECTIONSUMMARY": "巡检汇总表（每周）",
    "RF_W_LONGOPTICALPATH": "长光程分析仪运行状况检查记录表（每周）",
    "RF_W_OTHERDEVICECHECK": "其他设备运行状况检查记录表（每周）",
    "RF_W_PMCHECK": "颗粒物PM10/PM2.5自动监测分析仪运行状况检查记录表（每周）",
    "RF_W_STANDARD_ALL": "标准物质检查记录表（每周）",
    "RF_TW_CleanCuttingHead": "颗粒物切割头清洗记录表（两周）",
    "RF_TW_PmFlowCalibrate": "颗粒物流量校准记录表（两周）",
    "RF_TW_PmFlowCheck": "颗粒物流量检查记录表（两周）",
    "RF_M_GASEOUSCALICHECK": "气态分析仪校准检查记录表（月度）",
    "RF_M_GASEOUSCALIDEVICECHECK": "气态校准设备检查记录表（月度）",
    "RF_M_GASEOUSFLOWCHECK": "气态分析仪流量检查记录表（月度）",
    "RF_M_MANUALCOMPARISON": "手工比对记录表（月度）",
    "RF_M_MANUALCOMPARISONDETAIL": "手工比对明细记录表（月度）",
    "RF_M_MEMBRANEWEIGHING": "滤膜称重记录表（月度）",
    "RF_M_PMDEVICEMAINTAIN": "颗粒物仪器维护记录表（月度）",
    "RF_M_STATIONDEVICEMAINTAIN": "站点设备维护记录表（月度）",
    "RF_M_StationMaintainCheck": "站房维护检查记录表（月度）",
    "RF_Q_GASEOUSMULTIPOINT_CO": "一氧化碳（CO）分析仪多点校准记录表（季度）",
    "RF_Q_GASEOUSMULTIPOINT_NO2": "二氧化氮（NO2）分析仪多点校准记录表（季度）",
    "RF_Q_GASEOUSMULTIPOINT_O3": "臭氧（O3）分析仪多点校准记录表（季度）",
    "RF_Q_GASEOUSMULTIPOINT_SO2": "二氧化硫（SO2）分析仪多点校准记录表（季度）",
    "RF_Q_GASEOUSPRECISION_CO": "一氧化碳（CO）分析仪精密度检查记录表（季度）",
    "RF_Q_GASEOUSPRECISION_NO2": "二氧化氮（NO2）分析仪精密度检查记录表（季度）",
    "RF_Q_GASEOUSPRECISION_O3": "臭氧（O3）分析仪精密度检查记录表（季度）",
    "RF_Q_GASEOUSPRECISION_SO2": "二氧化硫（SO2）分析仪精密度检查记录表（季度）",
    "RF_Q_GaseousFlowCheck": "气态分析仪流量检查记录表（季度）",
    "RF_Q_LONGOPTICALPATH_NO2": "二氧化氮（NO2）长光程分析仪检查记录表（季度）",
    "RF_Q_LONGOPTICALPATH_O3": "臭氧（O3）长光程分析仪检查记录表（季度）",
    "RF_Q_LONGOPTICALPATH_SO2": "二氧化硫（SO2）长光程分析仪检查记录表（季度）",
    "RF_Q_PM10RUNSTATUSCHECK": "PM10分析仪运行状态检查记录表（季度）",
    "RF_Q_PM25RUNSTATUSCHECK": "PM2.5分析仪运行状态检查记录表（季度）",
    "RF_Q_PMPRESSURE": "颗粒物压力检查记录表（季度）",
    "RF_Q_STATIONDEVICECLEAN": "站点设备清洁记录表（季度）",
    "RF_Q_StationMaintainCheck": "站房维护检查记录表（季度）",
    "RF_Y_DEVICECHANGE": "设备更换记录表（年度）",
    "RF_Y_DEVICEREPAIR": "设备维修记录表（年度）",
    "RF_Y_PreventiveMaintenance": "预防性维护记录表（年度）",
    "RF_HY_GASEOUSCALIDEVICECHECK": "气态校准设备检查记录表",
    "RF_HY_O3VALUEPASS": "臭氧（O3）校准仪（工作标准）量值传递记录表（每季度）",
}


def rf_form_display_name(rf_table: str | None) -> str | None:
    if not rf_table:
        return None
    table = str(rf_table).strip()
    if not table:
        return None
    return RF_FORM_NAMES.get(table, "RF表单（中文名称待配置）")
