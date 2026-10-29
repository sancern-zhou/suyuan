@echo off
rem Guangdong data-ops daily job (02:30): master/full reload + daily increments
rem   + reconciliation + DQ gate (dq_check.py -> guangdong_sync.dq_results)
rem Keep this file pure ASCII.

setlocal
set RUNTIME_DIR=%~dp0..
set GD_PYTHON=M:\suyuan-tools\envs\backend_py311\Scripts\python.exe
set DBT_EXE=M:\suyuan-tools\data-ops-guangdong\dbt-venv\Scripts\dbt.exe

cd /d %RUNTIME_DIR%\sync

rem ---- daily_full tables: master data / no reliable incremental column ----
rem 2026-10-26: RF_W_INSPECTION / RF_W_INSPECTIONSUMMARY / RF_W_OTHERDEVICECHECK
rem and Alm_Home moved here from the incremental list - CREATEDATE/AlarmTime are
rem NULL on 5-56%% of rows, so watermark pulls structurally miss them.
rem The remaining declared-but-unscheduled RF_*/SEC_* form tables (frozen since
rem the 2026-10-24 cutover one-off pull) are also loaded here.
for %%t in (base_station base_device v_cityandregionanddepartment v_supcityandregionanddepartment SYS_USER SYS_DEPARTMENT PW_TASKITEM Sup_Mtc_TaskItem MTC_ORDERTASKITEM SEC_QcBlackOut OPA_DataReceiveRate Alm_Home RF_W_INSPECTION RF_W_INSPECTIONSUMMARY RF_W_OTHERDEVICECHECK RF_W_GrainCalibrationCheck_PM10 RF_W_GrainCalibrationCheck_PM25 RF_W_GrainCalibrationCheckAttach RF_W_LONGOPTICALPATH RF_W_STANDARD_ALL RF_TW_CleanCuttingHead RF_TW_PmFlowCalibrate RF_TW_PmFlowCheck RF_M_GASEOUSCALICHECK RF_M_GASEOUSCALIDEVICECHECK RF_M_GASEOUSFLOWCHECK RF_M_MANUALCOMPARISON RF_M_MANUALCOMPARISONDETAIL RF_M_MEMBRANEWEIGHING RF_M_PMDEVICEMAINTAIN RF_M_STATIONDEVICEMAINTAIN RF_M_StationMaintainCheck RF_Q_GASEOUSMULTIPOINT_CO RF_Q_GASEOUSMULTIPOINT_NO2 RF_Q_GASEOUSMULTIPOINT_O3 RF_Q_GASEOUSMULTIPOINT_SO2 RF_Q_GASEOUSPRECISION_CO RF_Q_GASEOUSPRECISION_NO2 RF_Q_GASEOUSPRECISION_O3 RF_Q_GASEOUSPRECISION_SO2 RF_Q_GaseousFlowCheck RF_Q_LONGOPTICALPATH_NO2 RF_Q_LONGOPTICALPATH_O3 RF_Q_LONGOPTICALPATH_SO2 RF_Q_PM10RUNSTATUSCHECK RF_Q_PM25RUNSTATUSCHECK RF_Q_PMPRESSURE RF_Q_STATIONDEVICECLEAN RF_Q_StationMaintainCheck RF_Y_DEVICECHANGE RF_Y_DEVICEREPAIR RF_Y_PreventiveMaintenance RF_SEC_INSPECTION RF_SEC_INSTRUMENTRECORD RF_SEC_MONITORINGCHECK RF_PM1MonitorInspection RF_BCMonitorInspection SEC_CHECKSCORE SEC_CHECKSCORE_SX SEC_CHECKSCORE_SXNEW Sup_RF_MonthNepheloMeterCheck Sup_RF_NepheloMeterCalibration RF_HY_EnvironmentHumidity RF_HY_GASEOUSCALIDEVICECHECK RF_HY_STATIONDEVICEMAINTAIN RF_HY_O3VALUEPASS RF_HY_VISIBILITYCALI RF_HY_NOXCONVERSIONRATE SEC_ScoreSheet Sup_ContractSetting Sup_DeviceLog Sup_Mtc_Device Sup_NMHC_CurveVerificationPoint Sup_NMHC_SystemBlank Sup_PowerFailureReport Sup_PowerFailureReportDetail Sup_QuarterlyReportUpload Sup_RF_GACMonthMaintain Sup_RF_GACQuarterMaintain Sup_RF_GACWeekMaintain Sup_RF_GACWeekMaintainByMARGA Sup_RF_GACYearMaintain Sup_RF_NMHC_QualityControlDataDetail Sup_RF_RuleItemTask Sup_RF_URGMonthMaintain Sup_RF_URGQuarterMaintain Sup_RF_URGWeekMaintain Sup_RF_URGYearMaintain Sup_RF_VOCQualityControlDataDetail Sup_RF_WaterSolubleIonsBlankCheck Sup_RF_WaterSolubleIonsCalibration Sup_RF_WaterSolubleIonsSingleCheck Sup_ScoreSheet Sup_Sec_ConfigData Sup_VOCs_CurveVerificationPoint Sup_VOCs_InternalStandard Sup_VOCs_SystemBlank SYS_USERSTATION SYS_DEPARTMENTSTATION RF_RuleItemTask Sec_ConfigData RF_HY_Humidity SEC_FlightCheck DRT_Beta DRT_GasAnalyzer DRT_GasAnalyzer_FiveParameters DRT_GasAnalyzer_NOX DRT_Teom PW_UNITPLAN) do (
    "%GD_PYTHON%" sync_table.py %%t --full >> sync_%%t.log 2>&1
)
rem working_order_details has no update column: full reload catches step status changes
"%GD_PYTHON%" sync_table.py working_order_details --full >> sync_working_order_details.log 2>&1

rem ---- daily incremental: forms/reports/plans (create-time watermarks) ----
for %%t in (PW_TASK RF_W_GASEOUSCHECK_SO2 RF_W_GASEOUSCHECK_NOX RF_W_GASEOUSCHECK_CO RF_W_GASEOUSCHECK_O3 RF_W_PMCHECK SEC_BlackOutReportDetail SEC_BlackOutReportTimespan QUL_QUALITYDATE Sup_DeviceDayCheck OPA_Performance OPA_STATIONPERFORMANCESCORE Sup_Device Sup_DeviceModel Sup_EffectRate Sup_MonthReport Sup_Pw_Task Sup_RF_BCYearMaintain Sup_RF_CO2DeviceMaintain Sup_RF_CO2HalfYearDeviceMaintain Sup_RF_CO2Inspection Sup_RF_CO2MulityPointCheck_Q Sup_RF_CO2YearDeviceMaintain Sup_RF_Calibration_NOy Sup_RF_ChannelFlowCalibration Sup_RF_ChromatotecFlowCheck Sup_RF_ChromatotecMonthMaintain Sup_RF_ChromatotecQuarterMaintain Sup_RF_ChromatotecWeekCheck Sup_RF_Co2Analyzerinspection Sup_RF_ConversionRate_NOy Sup_RF_DailyInspection Sup_RF_EquipmentMaintenance Sup_RF_EquipmentStatus Sup_RF_HeavyMetalInspection Sup_RF_LeakageRateCalibration_i Sup_RF_MaintenanceRecord Sup_RF_MonthDeviceMaintain_NOy Sup_RF_MultiCalibration Sup_RF_N2OAnalyzerinspection Sup_RF_NH3AnalyzerInspection Sup_RF_NH3Calibration Sup_RF_NH3ConversionRate Sup_RF_NH3DeviceMultipoint Sup_RF_NH3GASEOUSCALIDEVICECHECK Sup_RF_NH3InstrumentDetectionLimit Sup_RF_NH3InstrumentPrecision Sup_RF_NH3MonthDeviceMaintain Sup_RF_NH3ResponseTimeInspection Sup_RF_O3LaserRadarCalibration Sup_RF_O3LaserRadarCheck Sup_RF_O3LaserRadarMaintenance Sup_RF_OCECHalfYearCheck Sup_RF_OCECMonthCheck Sup_RF_OCECMultipointCheck Sup_RF_OCECQuarterhCheck Sup_RF_OCECSingleCheck Sup_RF_OCECWeekCheck Sup_RF_OCECYearCheck Sup_RF_PTRMSWeekCheck Sup_RF_QuarterlyEquipment Sup_RF_RepaireRecord Sup_RF_SpeedMeterMaintain Sup_RF_Turbidimeter Sup_RF_VisibilityMeter Sup_RF_Week_RadiationRecord Sup_RF_Year_RadiationCalibration Sup_RF_ZeroSpanCalibration Sup_RF_thybHalfYearMaintain Sup_RF_thybMonthMaintain Sup_RF_thybQuarterMaintain Sup_RF_thybWeekCheck Sup_RF_thybYearMaintain Sup_ReferenceMaterial sup_Pw_TaskItem) do (
    "%GD_PYTHON%" sync_table.py %%t >> sync_%%t.log 2>&1
)

rem ---- dbt build tag:daily ----
echo [%date% %time%] dbt build tag:daily >> sync_mart.log 2>&1
set "PYTHONUTF8=1"
"%DBT_EXE%" build --project-dir %RUNTIME_DIR%\dbt --profiles-dir %RUNTIME_DIR%\dbt --select tag:daily --no-use-colors >> sync_mart.log 2>&1
echo [%date% %time%] dbt build tag:daily exit=%errorlevel% >> sync_mart.log
if not "%errorlevel%"=="0" exit /b %errorlevel%

rem ---- reconciliation + DQ gate ----
for %%t in (working_orders working_order_details wo_commonfile_links base_station base_device) do (
    "%GD_PYTHON%" sync_table.py %%t --check >> sync_check.log 2>&1
)
"%GD_PYTHON%" dq_check.py >> sync_dq.log 2>&1
echo [%date% %time%] dq exit=%errorlevel% >> sync_dq.log

endlocal
