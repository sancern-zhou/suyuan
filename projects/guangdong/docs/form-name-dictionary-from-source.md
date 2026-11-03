# 表单名称字典（广东运维平台源码提取）

- 生成时间：2026-11-03；脚本 `.zcode/tmp/opa-audit-rules/extract_form_names.py`。
- 用途：P2 快赢——为 `rf_form_names.py`（RF_FORM_NAMES/SUP_FORM_NAMES）提供权威名称草案；
  类级 `<summary>` 为表单全称，枚举成员描述来自 `Enum/ReportForms/ReportFormsEnum.cs`。

## 主网表单枚举（ReportFormsEnum）

### RF_D_Enum

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `RF_D_GreenHouseCheck` | 1000 | 碳通量监系统运行状况表（每日） |

### RF_W_Enum

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `RF_W_Inspection` | 1000 | 站点巡检记录 |
| `RF_W_GaseousCheck` | 1001 | 分析仪运行状况检查记录表 |
| `RF_W_PmCheck` | 1002 | 颗粒物自动监测分析仪运行状况检查记录 |
| `RF_W_OtherDeviceCheck` | 1003 | 其他仪器、设备运行状况检查记录 |
| `RF_W_InspectionSummary` | 1004 | 空气直管站每周(次)巡检工作汇总表 |
| `RF_W_LongOpticalPath` | 1005 | 长光程(SO2,NO2,O3)分析仪器运行状况检查记录表 |
| `RF_W_Standard_ALL` | 1010 | 流量检查的仪器设备和标准流量 |
| `RF_W_GrainCalibrationCheck` | 1020 | 陕西省省控空气自动站颗粒监测仪校准检查表PM10 |
| `RF_BCMonitorInspection_Week` | 1030 | BC监测仪周巡查记录表 |
| `RF_PM1MonitorInspection_Week` | 1040 | PM1监测仪周巡查记录表 |

### RF_TW_Enum

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |

### RF_M_Enum

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `RF_M_StationDeviceMaintain` | 2000 | 站点设备维护记录 |
| `RF_M_GaseousFlowCheck` | 2001 | 气体分析仪流量检查记录表 |
| `RF_M_GaseousCaliCheck` | 2002 | 多气体动态校准仪校准检查记录表 |
| `SEC_CheckScore` | 2003 | 国家环境空气质量监测网城市站运维情况现场质控检查评分表 |
| `SEC_PerformanceManage` | 2004 | 国家环境空气质量监测网城市站运维绩效考核表 |
| `SEC_InspectionManage` | 2005 | 国家环境空气质量监测网城市站现场检查绩效考核表 |
| `RF_Week_OnlineCompare` | 2006 | 联机比对 |
| `RF_Week_ManualCompare` | 2007 | 手工比对 |
| `RF_M_ManualComparison` | 2008 | 颗粒物手工比对采样记录表 |
| `RF_M_PMDeviceMaintain` | 2009 | 站点维护记录表（每两月） |
| `RF_M_StationMaintainCheck` | 2010 | 运行维护记录表（月） |
| `RF_M_GASEOUSCALIDEVICECHECK` | 2011 | 多气体动态校准仪校准检查记录表（月） |
| `SEC_CheckScoreCnemc` | 2012 | 新国家环境空气质量监测网城市站运维情况现场质控检查评分表 |
| `RF_BCMonitorInspection_Month` | 2013 | BC监测仪月巡查记录表 |
| `RF_PM1MonitorInspection_Month` | 2014 | PM1监测仪月巡查记录表 |

### RF_Q_Enum

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `RF_Q_StationDeviceClean` | 3000 | 站点设备清洁记录 |
| `RF_Q_PmPressure` | 3001 | 颗粒物温度、压力校准记录表 |
| `RF_Q_PmRunStatusCheck` | 3002 | 颗粒物自动监测分析仪运行状况检查记录 |
| `RF_Q_GaseousMultipoint` | 3003 | 气体分析仪多点校准记录表 |
| `RF_Q_GaseousPrecision` | 3004 | 气体仪器精密度审核记录表 |
| `RF_Q_Pm10RunStatusCheck` | 3005 | 颗粒物PM10自动监测分析仪运行状况检查记录 |
| `RF_Q_Pm25RunStatusCheck` | 3006 | 颗粒物PM2.5自动监测分析仪运行状况检查记录 |
| `RF_Q_LongOpticalPath` | 3007 | 长光程(SO2,NO2,O3)分析仪单点校准检查记录表 |
| `RF_Q_StationMaintainCheck` | 3008 | 运行维护记录表（季） |
| `RF_Q_GaseousFlowCheck` | 3009 | 动态气体校准仪流量检查表 |
| `RF_PM1MonitorInspection_Quarter` | 3010 | PM1监测仪季度巡查记录表 |

### RF_HY_Enum

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `RF_HY_StationDeviceMaintain` | 4000 | 站点设备半年维护记录 |
| `RF_HY_NoxConversionRate` | 4001 | 氮氧化物分析仪钼炉转化率记录表 |
| `RF_HY_GaseousCaliDeviceCheck` | 4002 | 多气体动态校准仪校准检查记录表 |
| `RF_HY_O3ValuePass` | 4003 | 臭氧（O3）校准仪（工作标准）量值传递记录表 |
| `RF_HY_VisibilityCali` | 4004 | 能见度分析仪校准记录表 |
| `RF_HY_StationMaintainCheck` | 4005 | 运行维护记录表（半年） |
| `RF_HY_Results` | 4006 | 现场检查成效审核-气态 |
| `RF_HY_Results_Beta` | 4007 | 现场检查成效审核-β射线法 |
| `RF_HY_Results_Teom` | 4008 | 现场检查成效审核-振荡天平 |
| `RF_HY_EnvironmentHumidity` | 4009 | Beta射线法颗粒物连续监测仪环境湿度校准表 |
| `RF_HY_Results_FiveParameters` | 4010 | 气象五参数 |
| `RF_BCMonitorInspection_HalfYear` | 4011 | BC监测仪半年巡查记录表 |
| `RF_PM1MonitorInspection_HalfYear` | 4012 | PM1监测仪半年巡查记录表 |
| `RF_HY_Humidity` | 4013 | 颗粒物温度、压力校准记录表 |

### ResultsCreateOrderItem

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `RF_HY_Results_SO2` | 4006 |  |
| `RF_HY_Results_CO` | 4007 |  |
| `RF_HY_Results_O3` | 4008 |  |
| `RF_HY_Results_NOX` | 4009 |  |
| `RF_HY_Results_PM10Beta` | 4010 |  |
| `RF_HY_Results_PM10Teom` | 4011 |  |
| `RF_HY_Results_PM25Beta` | 4012 |  |
| `RF_HY_Results_PM25Teom` | 4013 |  |

### RF_Y_Enum

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `RF_Y_StandardSubstance` | 5000 | 标准物质记录表 |
| `RF_Y_DeviceRepair` | 5001 | 空气自动监测仪器设备检修记录表 |
| `RF_Y_DeviceChange` | 5002 | 备机更换记录表 |
| `RF_Y_PreventiveMaintenance` | 5003 |  |
| `RF_BCMonitorInspection_Year` | 5004 | BC监测仪年巡查记录表 |

### RF_SEC_Enum

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `RF_SEC_INSTRUMENTRECORD` | 6000 | 振荡天平法仪器记录表 |
| `RF_SEC_MONITORINGCHECK` | 6001 | 气态污染物监测仪器检查表表 |
| `RF_SEC_INSPECTION` | 6002 | 现场巡检检查单 |

### RF_TaskItem_Status

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `Finish` | 1 | 完成 |
| `UnFinish` | 0 | 未完成 |

### RF_Data_Status

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `Qualified` | 1 | 大于等于90合格 |
| `UnQualified` | 0 | 小于90不合格 |

### RF_Quality_Status

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `Higher` | 2 | 大于等于90 |
| `Middle` | 1 | 大于80小于等于90 |
| `Low` | 0 | 低于80 |

### RF_Score_Item

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |

### DRT_Enum

| 枚举成员 | 值 | 描述 |
| --- | ---: | --- |
| `DRT_Beta` | 1000 | β射线法PM2.5监测仪 |
| `DRT_TEOM` | 1001 | 微量振荡天平法颗粒物（PM2.5）监测仪 |
| `DRT_GasAnalyzer_NOX` | 1002 | 氮氧化物分析仪 |
| `DRT_GasAnalyzer` | 1003 | 二氧化硫分析仪 一氧化碳分析仪 臭氧分析仪 |
| `DRT_GasAnalyzer_FiveParameters` | 1006 | // 一氧化碳分析仪 // </summary> //DR_T_CO = 1004, // <summary> // 臭氧分析仪 // </summary> //DR_T_O3 = 1005, <summary> 气象五参数 |

## 组分站表单（Sup 实体类标题）

| 类/tag | 表单标题 | 文件 |
| --- | --- | --- |
| `RF_HY_GreenHouseCheck` | 碳通量监系统运行状况表（每周） | `Entity/Sup/QcForm/HalfYear/RF_HY_GreenHouseCheck.cs` |
| `RF_W_GreenHouseCheck` | 碳通量监系统运行状况表（每周） | `Entity/Sup/QcForm/Week/RF_W_GreenHouseCheck.cs` |
| `Sup_AchStepScore` |  | `Entity/Sup/OPA/Sup_Achievements.cs` |
| `Sup_Achievements` | 组分网绩效表 | `Entity/Sup/OPA/Sup_Achievements.cs` |
| `Sup_AchievementsLog` |  | `Entity/Sup/OPA/Sup_Achievements.cs` |
| `Sup_Achievements_His` |  | `Entity/Sup/OPA/Sup_Achievements.cs` |
| `Sup_BlackOutReport` |  | `Entity/Sup/Sup_PowerFailureReport.cs` |
| `Sup_ContractDevice` | 数据表实体类：Sup_ContractDevice | `Entity/Sup/OPA/Sup_ContractDevices.cs` |
| `Sup_ContractDevices` |  | `Entity/Sup/OPA/Sup_ContractDevices.cs` |
| `Sup_ContractMonths` |  | `Entity/Sup/OPA/Sup_ContractDevices.cs` |
| `Sup_ContractQuarter` |  | `Entity/Sup/OPA/Sup_ContractDevices.cs` |
| `Sup_ContractSetting` | 组分网合同主表 | `Entity/Sup/OPA/Sup_ContractSetting.cs` |
| `Sup_DepartmentDevice` | 设备 | `Entity/Sup/Sup_DepartmentDevice.cs` |
| `Sup_Device` | 设备 | `Entity/Sup/Sup_Device.cs` |
| `Sup_DeviceBrand` | 设备品牌 | `Entity/Sup/Sup_DeviceBrand.cs` |
| `Sup_DeviceDayCheck` |  | `Entity/Sup/Sup_DeviceDayCheck.cs` |
| `Sup_DeviceLife` |  | `Entity/Sup/Sup_Device.cs` |
| `Sup_DeviceLog` |  | `Entity/Sup/Sup_DeviceLog.cs` |
| `Sup_DeviceModel` | 设备型号 | `Entity/Sup/Sup_DeviceModel.cs` |
| `Sup_DeviceType` |  | `Entity/Sup/Sup_DeviceType.cs` |
| `Sup_EffectRate` |  | `Entity/Sup/Sup_EffectRate.cs` |
| `Sup_Instrument` | 仪器 | `Entity/Sup/Sup_Instrument.cs` |
| `Sup_InstrumentType` | 仪器类型 | `Entity/Sup/Sup_InstrumentType.cs` |
| `Sup_MonthReport` | SupMonthReport 月报管理 | `Entity/Sup/SupMonthReport.cs` |
| `Sup_Mtc_Device` |  | `Entity/Sup/Sup_Mtc_Device.cs` |
| `Sup_Mtc_TaskItem` |  | `Entity/Sup/Sup_Mtc_TaskItem.cs` |
| `Sup_NMHC_CurveVerificationPoint` | 曲线验证点 | `Entity/Sup/QcForm/Week/Sup_RF_Week_NMHCQC.cs` |
| `Sup_NMHC_SystemBlank` | 系统空白 | `Entity/Sup/QcForm/Week/Sup_RF_Week_NMHCQC.cs` |
| `Sup_PowerFailureReport` | 停电工单 | `Entity/Sup/Sup_PowerFailureReport.cs` |
| `Sup_PowerFailureReportDetail` |  | `Entity/Sup/Sup_PowerFailureReportTimespan.cs` |
| `Sup_PowerFailureReportTimespan` |  | `Entity/Sup/Sup_PowerFailureReportTimespan.cs` |
| `Sup_Pw_Task` |  | `Entity/Sup/Sup_Pw_Task.cs` |
| `Sup_Pw_TaskItem` |  | `Entity/Sup/Sup_Pw_Taskitem.cs` |
| `Sup_QCDevice` | 质控设备 | `Entity/Sup/QCDevice/Sup_QCDevice.cs` |
| `Sup_QCDeviceBrand` | 设备品牌 | `Entity/Sup/QCDevice/Sup_QCDeviceBrand.cs` |
| `Sup_QCDeviceModel` | 设备型号 | `Entity/Sup/QCDevice/Sup_QCDeviceModel.cs` |
| `Sup_QuarterlyReportUpload` |  | `Entity/Sup/Sup_QuarterlyReportUpload.cs` |
| `Sup_RF_Abstract` | 公用表单抽象类 | `Entity/Sup/QcForm/Sup_RF_Common.cs` |
| `Sup_RF_AmbientTemperature` |  | `Entity/Sup/QcForm/Week/Sup_RF_AmbientTemperature.cs` |
| `Sup_RF_AnalyzerInspection_NOy` |  | `Entity/Sup/QcForm/HalfYear/Sup_RF_AnalyzerInspection_NOy.cs` |
| `Sup_RF_Attex_Check` | 监测子站巡检记录表 | `Entity/Sup/QcForm/HighPrecision/Sup_RF_Attex_Check.cs` |
| `Sup_RF_BCFlowCheck` |  | `Entity/Sup/QcForm/Week/Sup_RF_BCFlowCheck.cs` |
| `Sup_RF_BCFlowVerificationCalibration` | MAGEE黑碳分析仪流量核查/校准表 | `Entity/Sup/QcForm/Quarter/Sup_RF_HCHOMaintainRecordDetail.cs` |
| `Sup_RF_BCHalfYearMaintain` |  | `Entity/Sup/QcForm/HalfYear/Sup_RF_BCHalfYearMaintain.cs` |
| `Sup_RF_BCMonthMaintain` |  | `Entity/Sup/QcForm/Month/Sup_RF_BCMonthMaintain.cs` |
| `Sup_RF_BCWeekInspection` |  | `Entity/Sup/QcForm/Week/Sup_RF_BCWeekInspection.cs` |
| `Sup_RF_BCYearMaintain` |  | `Entity/Sup/QcForm/Year/Sup_RF_BCYearMaintain.cs` |
| `Sup_RF_BlankTape` |  | `Entity/Sup/QcForm/Week/Sup_RF_BlankTape.cs` |
| `Sup_RF_CO2DeviceChange` | 数据表实体类：Sup_RF_CO2DeviceChange | `Entity/Sup/QcForm/CO2/Sup_RF_CO2DeviceChange.cs` |
| `Sup_RF_CO2DeviceMaintain` | 数据表实体类：Sup_RF_CO2DeviceMaintain | `Entity/Sup/QcForm/CO2/Sup_RF_CO2DeviceMaintain.cs` |
| `Sup_RF_CO2HalfYearDeviceMaintain` | 数据表实体类：Sup_RF_CO2HalfYearDeviceMaintain | `Entity/Sup/QcForm/CO2/Sup_RF_CO2HalfYearDeviceMaintain.cs` |
| `Sup_RF_CO2Inspection` | 数据表实体类：Sup_RF_CO2Inspection | `Entity/Sup/QcForm/CO2/Sup_RF_CO2Inspection.cs` |
| `Sup_RF_CO2MulityPointCheck_Q` | 数据表实体类：Sup_RF_CO2MulityPointCheck_Q | `Entity/Sup/QcForm/CO2/Sup_RF_CO2MulityPointCheck_Q.cs` |
| `Sup_RF_CO2QuarterDeviceMaintain` | 数据表实体类：Sup_RF_CO2QuarterDeviceMaintain | `Entity/Sup/QcForm/CO2/Sup_RF_CO2QuarterDeviceMaintain.cs` |
| `Sup_RF_CO2YearDeviceMaintain` | 数据表实体类：Sup_RF_CO2YearDeviceMaintain | `Entity/Sup/QcForm/CO2/Sup_RF_CO2YearDeviceMaintain.cs` |
| `Sup_RF_Calibration_NOy` |  | `Entity/Sup/QcForm/Week/Sup_RF_Calibration_NOy.cs` |
| `Sup_RF_ChannelFlowCalibration` | 数据表实体类：Sup_RF_ChannelFlowCalibration | `Entity/Sup/QcForm/Sup_RF_ChannelFlowCalibration.cs` |
| `Sup_RF_ChannelFlowCalibration_Detail` |  | `Entity/Sup/QcForm/Sup_RF_ChannelFlowCalibration.cs` |
| `Sup_RF_ChromatotecFlowCheck` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_ChromatotecFlowCheck.cs` |
| `Sup_RF_ChromatotecMonthMaintain` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_ChromatotecMonthMaintain.cs` |
| `Sup_RF_ChromatotecQuarterMaintain` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_ChromatotecQuarterMaintain.cs` |
| `Sup_RF_ChromatotecWeekCheck` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_ChromatotecWeekCheck.cs` |
| `Sup_RF_ChromatotecYearMaintain` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_ChromatotecYearMaintain.cs` |
| `Sup_RF_Co2Analyzerinspection` |  | `Entity/Sup/QcForm/Week/Sup_RF_Co2Analyzerinspection.cs` |
| `Sup_RF_CollectionCalibration` |  | `Entity/Sup/QcForm/Month/Sup_RF_CollectionCalibration.cs` |
| `Sup_RF_Common` | 公用表单非抽象类 | `Entity/Sup/QcForm/Sup_RF_Common.cs` |
| `Sup_RF_ConsumablesReplace` |  | `Entity/Sup/QcForm/Week/Sup_RF_ConsumablesReplace.cs` |
| `Sup_RF_ConversionRate_NOy` |  | `Entity/Sup/QcForm/Month/Sup_RF_ConversionRate_NOy.cs` |
| `Sup_RF_DailyInspection` |  | `Entity/Sup/QcForm/Week/Sup_RF_DailyInspection.cs` |
| `Sup_RF_Day_HONOCheck` | HONO监测仪 日巡检表 | `Entity/Sup/QcForm/Week/Sup_RF_Day_HONOCheck.cs` |
| `Sup_RF_Day_HONOOnlineCheck` | HONO监测仪 日 线上巡检表 | `Entity/Sup/QcForm/Week/Sup_RF_Day_HONOOnlineCheck.cs` |
| `Sup_RF_DeviceFlowCheck` |  | `Entity/Sup/QcForm/Week/Sup_RF_DeviceFlowCheck.cs` |
| `Sup_RF_DeviceMultipoint_NOy` |  | `Entity/Sup/QcForm/HalfYear/Sup_RF_DeviceMultipoint_NOy.cs` |
| `Sup_RF_Diaphragm` | 数据表实体类：Sup_RF_Diaphragm | `Entity/Sup/QcForm/Sup_RF_Diaphragm.cs` |
| `Sup_RF_DiaphragmCheck` | 聚光-重金属标准膜片核查（季度） | `Entity/Sup/QcForm/Quarter/Sup_RF_DiaphragmCheck.cs` |
| `Sup_RF_EmergencyResponse` |  | `Entity/Sup/QcForm/Week/Sup_RF_EmergencyResponse.cs` |
| `Sup_RF_EnvironmentalCheck` |  | `Entity/Sup/QcForm/Week/Sup_RF_EnvironmentalCheck.cs` |
| `Sup_RF_EquipmentMaintenance` |  | `Entity/Sup/QcForm/Week/Sup_RF_EquipmentMaintenance.cs` |
| `Sup_RF_EquipmentStatus` |  | `Entity/Sup/QcForm/Week/Sup_RF_EquipmentStatus.cs` |
| `Sup_RF_FaultRecord` |  | `Entity/Sup/QcForm/Week/Sup_RF_FaultRecord.cs` |
| `Sup_RF_GACMonthMaintain` |  | `Entity/Sup/QcForm/Month/Sup_RF_GACMonthMaintain.cs` |
| `Sup_RF_GACQuarterMaintain` |  | `Entity/Sup/QcForm/Quarter/Sup_RF_GACQuarterMaintain.cs` |
| `Sup_RF_GACWeekMaintain` |  | `Entity/Sup/QcForm/Week/Sup_RF_GACWeekMaintain.cs` |
| `Sup_RF_GACWeekMaintainByMARGA` |  | `Entity/Sup/QcForm/Week/Sup_RF_GACWeekMaintainByMARGA.cs` |
| `Sup_RF_GACYearMaintain` |  | `Entity/Sup/QcForm/Year/Sup_RF_GACYearMaintain.cs` |
| `Sup_RF_HCHOCollectPercent` | 甲醛仪捕集效率测定结果记录表 | `Entity/Sup/QcForm/Quarter/Sup_RF_HCHOMaintainRecordDetail.cs` |
| `Sup_RF_HCHODetectionLimit` | 甲醛仪检出限测定结果记录表 | `Entity/Sup/QcForm/Quarter/Sup_RF_HCHOMaintainRecordDetail.cs` |
| `Sup_RF_HCHOMLinearError` | 甲醛仪线性误差测定结果记录表 | `Entity/Sup/QcForm/Quarter/Sup_RF_HCHOMaintainRecordDetail.cs` |
| `Sup_RF_HCHORepeatTest` | 甲醛仪重复性测定结果记录表 | `Entity/Sup/QcForm/Quarter/Sup_RF_HCHOMaintainRecordDetail.cs` |
| `Sup_RF_HONOConsumablesReplace` | HONO监测仪 耗材更换表 | `Entity/Sup/QcForm/Week/Sup_RF_HONOConsumablesReplace.cs` |
| `Sup_RF_HP_Accuracy` | 高精度分析仪准确度审核记录表 | `Entity/Sup/QcForm/HighPrecision/Sup_RF_HP_Accuracy.cs` |
| `Sup_RF_HP_Calibration` | 高精度仪器运行状况检查/校准记录表 | `Entity/Sup/QcForm/HighPrecision/Sup_RF_HP_Calibration.cs` |
| `Sup_RF_HP_Calibration_Detail1` |  | `Entity/Sup/QcForm/HighPrecision/Sup_RF_HP_Calibration.cs` |
| `Sup_RF_HP_Calibration_Detail2` |  | `Entity/Sup/QcForm/HighPrecision/Sup_RF_HP_Calibration.cs` |
| `Sup_RF_HP_Comparability` | 高精度分析仪可比性审核记录表 | `Entity/Sup/QcForm/HighPrecision/Sup_RF_HP_Comparability.cs` |
| `Sup_RF_HP_Config` |  | `Entity/Sup/QcForm/HighPrecision/Sup_RF_HP_Calibration.cs` |
| `Sup_RF_HP_DalyHealth` | 高精度分析仪每日运行状况表 | `Entity/Sup/QcForm/HighPrecision/Sup_RF_HP_DalyHealth.cs` |
| `Sup_RF_HP_Precision` | 高精度分析仪精密度审核记录表 | `Entity/Sup/QcForm/HighPrecision/Sup_RF_HP_Precision.cs` |
| `Sup_RF_HP_StationCheck` | 监测子站巡检记录表 | `Entity/Sup/QcForm/HighPrecision/Sup_RF_HP_StationCheck.cs` |
| `Sup_RF_HY_NMHCMaintenanceRecord` | Sup_RF_HY_NMHCMaintenanceRecord 甲烷/非甲烷总烃分析仪半年维护记录表 磐诺、中兴 | `Entity/Sup/QcForm/HalfYear/Sup_RF_HY_NMHCMaintenanceRecord.cs` |
| `Sup_RF_HalfYearNepheloMeterCheck` | 数据表实体类：Sup_RF_HalfYearNepheloMeterCheck | `Entity/Sup/QcForm/NepheloMeter/Sup_RF_HalfYearNepheloMeterCheck.cs` |
| `Sup_RF_HalfYear_HONOCheck` | HONO监测仪 年中巡检表 | `Entity/Sup/QcForm/HalfYear/Sup_RF_HalfYear_HONOCheck.cs` |
| `Sup_RF_HeavyMetalInspection` | 数据表实体类：Sup_RF_HeavyMetalInspection | `Entity/Sup/QcForm/Sup_RF_HeavyMetalInspection.cs` |
| `Sup_RF_HeavyMetalQuality` |  | `Entity/Sup/QcForm/Week/Sup_RF_HeavyMetalQuality.cs` |
| `Sup_RF_InstrumentDetectionLimit_NOy` |  | `Entity/Sup/QcForm/Year/Sup_RF_InstrumentDetectionLimit_NOy.cs` |
| `Sup_RF_LeakageRateCalibration_i` |  | `Entity/Sup/QcForm/Week/Sup_RF_LeakageRateCalibration_i.cs` |
| `Sup_RF_LeakageRateCheck_i` |  | `Entity/Sup/QcForm/Week/Sup_RF_LeakageRateCheck_i.cs` |
| `Sup_RF_MSFlowCheck` | 禾信-单颗粒飞行时间质谱流量核查（每月） | `Entity/Sup/QcForm/Month/Sup_RF_MSFlowCheck.cs` |
| `Sup_RF_MSParticleSizeCalibration` | 禾信-单颗粒飞行时间质谱粒径核查校准表（季度） | `Entity/Sup/QcForm/Quarter/Sup_RF_MSParticleSizeCalibration.cs` |
| `Sup_RF_MSQualityCalibration` | 禾信-单颗粒飞行时间质谱质量核查校准表（季度） | `Entity/Sup/QcForm/Quarter/Sup_RF_MSQualityCalibration.cs` |
| `Sup_RF_MSRoutineCheck` | 禾信质谱例行巡检记录表（每周） | `Entity/Sup/QcForm/Week/Sup_RF_MSRoutineCheck.cs` |
| `Sup_RF_MSSPAMSCalibration` | 禾信质谱SPAMS粒径和质量校准表 | `Entity/Sup/QcForm/Quarter/Sup_RF_MSSPAMSCalibration.cs` |
| `Sup_RF_MTHMultipointCalibration` | 甲烷、总烃多点校准及线性记录表 | `Entity/Sup/QcForm/Year/Sup_RF_MTHMultipointCalibration.cs` |
| `Sup_RF_MTHNMHCAnalyzer` | NMHC分析仪巡检表 | `Entity/Sup/QcForm/Week/Sup_RF_MTHNMHCAnalyzer.cs` |
| `Sup_RF_MTHZeroSpanCalibration` | Aurora3000_浊度计零跨核查与校准记录表（每周） | `Entity/Sup/QcForm/Week/Sup_RF_MTHZeroSpanCalibration.cs` |
| `Sup_RF_MaintenanceRecord` |  | `Entity/Sup/QcForm/Week/Sup_RF_MaintenanceRecord.cs` |
| `Sup_RF_MonitorInspection` |  | `Entity/Sup/QcForm/Week/Sup_RF_MonitorInspection.cs` |
| `Sup_RF_MonthDeviceMaintain_NOy` |  | `Entity/Sup/QcForm/Month/Sup_RF_MonthDeviceMaintain_NOy.cs` |
| `Sup_RF_MonthNepheloMeterCheck` | 数据表实体类：Sup_RF_MonthNepheloMeterCheck | `Entity/Sup/QcForm/NepheloMeter/Sup_RF_MonthNepheloMeterCheck.cs` |
| `Sup_RF_Month_HONOCheck` | HONO监测仪 月巡检表 | `Entity/Sup/QcForm/Month/Sup_RF_Month_HONOCheck.cs` |
| `Sup_RF_Month_HONOTest` | HONO监测仪 月 检出限测试表 | `Entity/Sup/QcForm/Month/Sup_RF_Month_HONOTest.cs` |
| `Sup_RF_Month_THLiDAR` |  | `Entity/Sup/QcForm/Month/Sup_RF_Month_THLiDAR.cs` |
| `Sup_RF_Month_YT_FlowCalibration` | Sup_RF_Month_YT_FlowCalibration 甲烷非甲烷总烃在线分析仪采样流量校准记录表 优泰 | `Entity/Sup/QcForm/Month/Sup_RF_Month_YT_FlowCalibration.cs` |
| `Sup_RF_Month_YT_LeakChecking` | Sup_RF_Month_YT_LeakChecking 甲烷非甲烷总烃在线分析仪验漏记录表 优泰 | `Entity/Sup/QcForm/Month/Sup_RF_Month_YT_LeakChecking.cs` |
| `Sup_RF_MultiCalibration` |  | `Entity/Sup/QcForm/Week/Sup_RF_MultiCalibration.cs` |
| `Sup_RF_N2OAnalyzerinspection` |  | `Entity/Sup/QcForm/Week/Sup_RF_N2OAnalyzerinspection.cs` |
| `Sup_RF_NH3AnalyzerInspection` |  | `Entity/Sup/QcForm/Week/Sup_RF_NH3AnalyzerInspection.cs` |
| `Sup_RF_NH3Calibration` | 数据表实体类：Sup_RF_NH3Calibration | `Entity/Sup/QcForm/NH3/Sup_RF_NH3Calibration.cs` |
| `Sup_RF_NH3ConversionRate` | 数据表实体类：Sup_RF_NH3ConversionRate | `Entity/Sup/QcForm/NH3/Sup_RF_NH3ConversionRate.cs` |
| `Sup_RF_NH3DeviceMultipoint` | 数据表实体类：Sup_RF_NH3DeviceMultipoint | `Entity/Sup/QcForm/NH3/Sup_RF_NH3DeviceMultipoint.cs` |
| `Sup_RF_NH3GASEOUSCALIDEVICECHECK` | 数据表实体类：Sup_RF_NH3GASEOUSCALIDEVICECHECK | `Entity/Sup/QcForm/NH3/Sup_RF_NH3GASEOUSCALIDEVICECHECK.cs` |
| `Sup_RF_NH3InstrumentDetectionLimit` | 数据表实体类：Sup_RF_NH3InstrumentDetectionLimit | `Entity/Sup/QcForm/NH3/Sup_RF_NH3InstrumentDetectionLimit.cs` |
| `Sup_RF_NH3InstrumentPrecision` | 数据表实体类：Sup_RF_NH3InstrumentPrecision | `Entity/Sup/QcForm/NH3/Sup_RF_NH3InstrumentPrecision.cs` |
| `Sup_RF_NH3MonthDeviceMaintain` | 数据表实体类：Sup_RF_NH3MonthDeviceMaintain | `Entity/Sup/QcForm/NH3/Sup_RF_NH3MonthDeviceMaintain.cs` |
| `Sup_RF_NH3ResponseTimeInspection` | 数据表实体类：Sup_RF_NH3ResponseTimeInspection | `Entity/Sup/QcForm/NH3/Sup_RF_NH3ResponseTimeInspection.cs` |
| `Sup_RF_NH3StandardMaterial1` | 数据表实体类：Sup_RF_NH3StandardMaterial1 | `Entity/Sup/QcForm/NH3/Sup_RF_NH3StandardMaterial1.cs` |
| `Sup_RF_NH3TraceabilityDlivery` | 数据表实体类：Sup_RF_NH3TraceabilityDlivery | `Entity/Sup/QcForm/NH3/Sup_RF_NH3TraceabilityDlivery.cs` |
| `Sup_RF_NMHCAnalyzerRecord` | Sup_RF_NMHCAnalyzerRecord 甲烷/非甲烷分析仪检出限、准确定、稳定性测试记录表-每年 磐诺、中兴 | `Entity/Sup/QcForm/Year/Sup_RF_NMHCAnalyzerRecord.cs` |
| `Sup_RF_NMHC_QualityControlDataDetail` | 校准曲线 | `Entity/Sup/QcForm/Week/Sup_RF_Week_NMHCQC.cs` |
| `Sup_RF_NepheloMeterCalibration` | 数据表实体类：Sup_RF_NepheloMeterCalibration | `Entity/Sup/QcForm/NepheloMeter/Sup_RF_NepheloMeterCalibration.cs` |
| `Sup_RF_NepheloMeterTemperature` | 数据表实体类：Sup_RF_NepheloMeterTemperature | `Entity/Sup/QcForm/NepheloMeter/Sup_RF_NepheloMeterTemperature.cs` |
| `Sup_RF_O3LaserRadarBackupDeviceChange` | 臭氧激光雷达零备件更换记录 | `Entity/Sup/QcForm/Week/Sup_RF_O3LaserRadarBackupDeviceChange.cs` |
| `Sup_RF_O3LaserRadarBackupDeviceChangeDetail` | 臭氧激光雷达零备件更换记录子表 | `Entity/Sup/QcForm/Week/Sup_RF_O3LaserRadarBackupDeviceChange.cs` |
| `Sup_RF_O3LaserRadarCalibration` |  | `Entity/Sup/QcForm/Quarter/Sup_RF_O3LaserRadarCalibration.cs` |
| `Sup_RF_O3LaserRadarCheck` | 臭氧激光雷达巡检记录表（每周） | `Entity/Sup/QcForm/Week/Sup_RF_O3LaserRadarCheck.cs` |
| `Sup_RF_O3LaserRadarExceptionHandler` | 异常情况应急处置记录表 | `Entity/Sup/QcForm/Week/Sup_RF_O3LaserRadarExceptionHandler.cs` |
| `Sup_RF_O3LaserRadarExceptionHandlerDetail` | 异常情况应急处置记录表子表 | `Entity/Sup/QcForm/Week/Sup_RF_O3LaserRadarExceptionHandler.cs` |
| `Sup_RF_O3LaserRadarMaintenance` | 臭氧激光雷达维护记录（每月） | `Entity/Sup/QcForm/Month/Sup_RF_O3LaserRadarMaintenance.cs` |
| `Sup_RF_O3LidarExceptionHandling` | 臭氧激光雷达 异常情况应急处置记录表 | `Entity/Sup/QcForm/Week/Sup_RF_O3LidarExceptionHandling.cs` |
| `Sup_RF_O3LidarFourQuadrant` | 臭氧激光雷达四象限检查记录表 | `Entity/Sup/QcForm/O3Lidar/Sup_RF_O3LidarFourQuadrant.cs` |
| `Sup_RF_O3LidarGen2_Check` | 二代臭氧雷达巡检表 | `Entity/Sup/QcForm/O3Lidar/Sup_RF_O3LidarGen2_Check.cs` |
| `Sup_RF_O3LidarRepair` | HONO监测仪 周巡检表 | `Entity/Sup/QcForm/Week/Sup_RF_O3LidarRepair.cs` |
| `Sup_RF_O3LidarSpareParts` | 臭氧激光雷达 零备件更换记录 | `Entity/Sup/QcForm/Week/Sup_RF_O3LidarSpareParts.cs` |
| `Sup_RF_OCECCheck` |  | `Entity/Sup/QcForm/Month/Sup_RF_OCECCheck.cs` |
| `Sup_RF_OCECHalfYearCheck` | 数据表实体类：Sup_RF_OCECHalfYearCheck | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECHalfYearCheck.cs` |
| `Sup_RF_OCECJGFlowCalibration` | 聚光-OCEC通道流量校准表（每年） | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECJGFlowCalibration.cs` |
| `Sup_RF_OCECJGFlowCheck` | 聚光-OCEC通道流量核查表（每年） | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECJGFlowCheck.cs` |
| `Sup_RF_OCECJGMultipointCheck` | 聚光-OCEC多点蔗糖溶液校准（每季度） | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECJGMultipointCheck.cs` |
| `Sup_RF_OCECJGSingleCheck` | 聚光-OCEC单点蔗糖溶液核查（每2周） | `Entity/Sup/QcForm/TwoWeek/Sup_RF_OCECJGSingleCheck.cs` |
| `Sup_RF_OCECJGWeekCheck` | 聚光-OCEC例行巡检记录表（每周） | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECJGWeekCheck.cs` |
| `Sup_RF_OCECMonthCheck` | 数据表实体类：Sup_RF_OCECMonthCheck | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECMonthCheck.cs` |
| `Sup_RF_OCECMultipointCheck` |  | `Entity/Sup/QcForm/Quarter/Sup_RF_OCECMultipointCheck.cs` |
| `Sup_RF_OCECQuarterhCheck` | 数据表实体类：Sup_RF_OCECQuarterhCheck | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECQuarterhCheck.cs` |
| `Sup_RF_OCECSamplingFlowCheck` | Sunset-OCEC采样流量核查校准表（每月） | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECSamplingFlowCheck.cs` |
| `Sup_RF_OCECSingleCheck` |  | `Entity/Sup/QcForm/TwoWeek/Sup_RF_OCECSingleCheck.cs` |
| `Sup_RF_OCECSunsetFlowCalibration` | Sunset-OCEC通道流量校准表（每年） | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECSunsetFlowCalibration.cs` |
| `Sup_RF_OCECSunsetFlowCheck` | Sunset-OCEC通道流量核查表（每年） | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECSunsetFlowCheck.cs` |
| `Sup_RF_OCECWeekCheck` | 数据表实体类：Sup_RF_OCECWeekCheck | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECWeekCheck.cs` |
| `Sup_RF_OCECYearCheck` | 数据表实体类：Sup_RF_OCECYearCheck | `Entity/Sup/QcForm/OCEC/Sup_RF_OCECYearCheck.cs` |
| `Sup_RF_OcecEnvironmentCheck` | 聚光-重金属标准膜片核查（季度） | `Entity/Sup/QcForm/Quarter/Sup_RF_OcecEnvironmentCheck.cs` |
| `Sup_RF_OcecFlowVerificationCheck` | 聚光-重金属标准膜片核查（季度） | `Entity/Sup/QcForm/Quarter/Sup_RF_OcecFlowVerificationCheck.cs` |
| `Sup_RF_OcecHeliumMethaneCheck` | 聚光-重金属标准膜片核查（季度） | `Entity/Sup/QcForm/Quarter/Sup_RF_OcecHeliumMethaneCheck.cs` |
| `Sup_RF_OcecOrganicCarbonCheck` | 聚光-重金属标准膜片核查（季度） | `Entity/Sup/QcForm/Quarter/Sup_RF_OcecOrganicCarbonCheck.cs` |
| `Sup_RF_PANsEmergencyDeal` | 异常情况应急处置记录表 | `Entity/Sup/QcForm/Month/Sup_RF_PANsEmergencyDeal.cs` |
| `Sup_RF_PANsFlowCheck` | PANs校准仪流量检查记录表（每月） | `Entity/Sup/QcForm/Month/Sup_RF_PANsFlowCheck.cs` |
| `Sup_RF_PANsItemReplace` | 设备耗材零备件更换记录表（每月） | `Entity/Sup/QcForm/Month/Sup_RF_PANsItemReplace.cs` |
| `Sup_RF_PANsRepeatabilityCheck` | PANs重复性检查记录表（每年） | `Entity/Sup/QcForm/Year/Sup_RF_PANsRepeatabilityCheck.cs` |
| `Sup_RF_PANsStabilityCheck` | PANs稳定性检查记录表（每年） | `Entity/Sup/QcForm/Year/Sup_RF_PANsStabilityCheck.cs` |
| `Sup_RF_PANsWeekCheck` | PANs例行巡检维护记录表（每周） | `Entity/Sup/QcForm/Week/Sup_RF_PANsWeekCheck.cs` |
| `Sup_RF_PANsWorkCurveCalibration` | PANs工作曲线校准记录表（每月） | `Entity/Sup/QcForm/Month/Sup_RF_PANsWorkCurveCalibration.cs` |
| `Sup_RF_PDLIYearCheck` | 武汉天虹VOC例行巡检记录表（每周） | `Entity/Sup/QcForm/PDLI/Sup_RF_PDLIYearCheck.cs` |
| `Sup_RF_PEWeekCheck` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_PEWeekCheck.cs` |
| `Sup_RF_PM1MonitorInspection` |  | `Entity/Sup/QcForm/Week/Sup_RF_PM1MonitorInspection.cs` |
| `Sup_RF_POnLineAnalyzerRepair` |  | `Entity/Sup/QcForm/Week/Sup_RF_POnLineAnalyzerRepair.cs` |
| `Sup_RF_PRInspectionRecord` | 光解速率巡检维护记录表（每周） | `Entity/Sup/QcForm/Week/Sup_RF_PRInspectionRecord.cs` |
| `Sup_RF_PTRMSWeekCheck` |  | `Entity/Sup/QcForm/PTRMS/Sup_RF_PTRMSWeekCheck.cs` |
| `Sup_RF_PTRMS_DayCheck` | PTR-MS每周远程检查表 | `Entity/Sup/QcForm/PTRMS/Sup_RF_PTRMS_DayCheck.cs` |
| `Sup_RF_PTRMS_WeekCheck` | PTR-MS每周远程检查表 | `Entity/Sup/QcForm/PTRMS/Sup_RF_PTRMS_WeekCheck.cs` |
| `Sup_RF_PTR_MSQuality` | PTR-MS质控数据表 | `Entity/Sup/QcForm/Week/Sup_RF_PTR_MSQuality.cs` |
| `Sup_RF_PaperTapeRecord` | 聚光-重金属纸带空白记录表（更换纸带时，每季度更换1次） | `Entity/Sup/QcForm/Quarter/Sup_RF_PaperTapeRecord.cs` |
| `Sup_RF_QPlanningStatistics` |  | `Entity/Sup/QcForm/Week/Sup_RF_QPlanningStatistics.cs` |
| `Sup_RF_QualityCalibration` |  | `Entity/Sup/QcForm/Week/Sup_RF_QualityCalibration.cs` |
| `Sup_RF_QualityCheck` | 天瑞-重金属质量标准核查表（季度） | `Entity/Sup/QcForm/Quarter/Sup_RF_QualityCheck.cs` |
| `Sup_RF_Quarter_HONOCheck` | HONO监测仪 季度巡检表 | `Entity/Sup/QcForm/Quarter/Sup_RF_Quarter_HONOCheck.cs` |
| `Sup_RF_Quarter_THLiDAR` |  | `Entity/Sup/QcForm/Quarter/Sup_RF_Quarter_THLiDAR.cs` |
| `Sup_RF_Quarter_YT_NMHCRecord` | Sup_RF_Quarter_YT_NMHCRecord 甲烷非甲烷总烃在线分析仪记录表 优泰 | `Entity/Sup/QcForm/Quarter/Sup_RF_Quarter_YT_NMHCRecord.cs` |
| `Sup_RF_QuarterlyEquipment` |  | `Entity/Sup/QcForm/Week/Sup_RF_QuarterlyEquipment.cs` |
| `Sup_RF_RULEITEMVOCs` | VOCs（AMA-VOCs例行巡检记录表（每周） | `Entity/Sup/QcForm/VOCs/Sup_RF_RULEITEMVOCs.cs` |
| `Sup_RF_RepaireRecord` |  | `Entity/Sup/QcForm/Week/Sup_RF_RepaireRecord.cs` |
| `Sup_RF_RoutineInspection` |  | `Entity/Sup/QcForm/Week/Sup_RF_RoutineInspection.cs` |
| `Sup_RF_Rule` |  | `Entity/Sup/Sup_RF_RuleItem.cs` |
| `Sup_RF_RuleItem` |  | `Entity/Sup/Sup_RF_RuleItem.cs` |
| `Sup_RF_RuleItemTask` |  | `Entity/Sup/Sup_RF_RuleItemTask.cs` |
| `Sup_RF_RuleItem_Relevance` |  | `Entity/Sup/Sup_RF_RuleItem.cs` |
| `Sup_RF_SpanCalibration` |  | `Entity/Sup/QcForm/Week/Sup_RF_SpanCalibration.cs` |
| `Sup_RF_SpeedMeterMaintain` |  | `Entity/Sup/QcForm/Week/Sup_RF_SpeedMeterMaintain.cs` |
| `Sup_RF_SpeedReplacementParts` |  | `Entity/Sup/QcForm/Week/Sup_RF_SpeedReplacementParts.cs` |
| `Sup_RF_StandardGas` |  | `Entity/Sup/QcForm/Week/Sup_RF_StandardGas.cs` |
| `Sup_RF_StandardMaterial_NOy` |  | `Entity/Sup/QcForm/AsNeed/Sup_RF_StandardMaterial_NOy.cs` |
| `Sup_RF_TSI3321Inspection` | 数据表实体类：Sup_RF_TSI3321Inspection | `Entity/Sup/QcForm/Week/Sup_RF_TSI3321Inspection.cs` |
| `Sup_RF_TSI3375Inspection` | 数据表实体类：Sup_RF_TSI3375Inspection | `Entity/Sup/QcForm/Week/Sup_RF_TSI3775Inspection.cs` |
| `Sup_RF_TSI3376Inspection` | 数据表实体类：Sup_RF_TSI3375Inspection | `Entity/Sup/QcForm/Week/Sup_RF_TSI3776Inspection.cs.cs` |
| `Sup_RF_TSIBypassCalibration` | 数据表实体类：Sup_RF_TSIBypassCalibration | `Entity/Sup/QcForm/Month/Sup_RF_TSIBypassCalibration.cs` |
| `Sup_RF_TSIFlowCheck` | 数据表实体类：Sup_RF_TSIFlowCheck | `Entity/Sup/QcForm/Week/Sup_RF_TSIFlowCheck.cs` |
| `Sup_RF_TSIFlowCheckRecord` | 粒径谱仪流量核查记录表（每月） | `Entity/Sup/QcForm/Month/Sup_RF_TSIFlowCheckRecord.cs` |
| `Sup_RF_TSIImpactorCalibration` | 数据表实体类：Sup_RF_TSIImpactorCalibration | `Entity/Sup/QcForm/Month/Sup_RF_TSIImpactorCalibration.cs` |
| `Sup_RF_TSIMonthMaintain` | 数据表实体类：Sup_RF_TSIMonthMaintain | `Entity/Sup/QcForm/Month/Sup_RF_TSIMonthMaintain.cs` |
| `Sup_RF_TSIQuarterMaintain` | 数据表实体类：Sup_RF_TSIQuarterMaintain | `Entity/Sup/QcForm/Quarter/Sup_RF_TSIQuarterMaintain.cs` |
| `Sup_RF_TSIRoutineCheck` | 粒径谱仪例行巡检记录表（每周） | `Entity/Sup/QcForm/Week/Sup_RF_TSIRoutineCheck.cs` |
| `Sup_RF_TSISheathCalibration` | 数据表实体类：Sup_RF_TSISheathCalibration | `Entity/Sup/QcForm/Month/Sup_RF_TSISheathCalibration.cs` |
| `Sup_RF_TSIYearMaintain` | 数据表实体类：Sup_RF_TSIYearMaintain | `Entity/Sup/QcForm/Year/Sup_RF_TSIYearMaintain.cs` |
| `Sup_RF_TotalSolarRadiation` |  | `Entity/Sup/QcForm/Week/Sup_RF_TotalSolarRadiation.cs` |
| `Sup_RF_TraceabilityDlivery_NOy` |  | `Entity/Sup/QcForm/AsNeed/Sup_RF_TraceabilityDlivery_NOy.cs` |
| `Sup_RF_TurbidiMeterCalibration` | Aurora3000_浊度计零跨核查与校准记录表（每周） | `Entity/Sup/QcForm/Week/Sup_RF_TurbidiMeterCalibration.cs` |
| `Sup_RF_TurbidiMeterRoutineCheck` | Aurora3000_浊度计巡检维护记录表（每周） | `Entity/Sup/QcForm/Week/Sup_RF_TurbidiMeterRoutineCheck.cs` |
| `Sup_RF_TurbidiMeterSamplingCheck` | Aurora3000_浊度计采样流量核查（每月） | `Entity/Sup/QcForm/Month/Sup_RF_TurbidiMeterSamplingCheck.cs` |
| `Sup_RF_TurbidiMeterTAPRecord` | Aurora3000_浊度计温度大气压记录表（每年） | `Entity/Sup/QcForm/Year/Sup_RF_TurbidiMeterTAPRecord.cs` |
| `Sup_RF_Turbidimeter` |  | `Entity/Sup/QcForm/Week/Sup_RF_Turbidimeter.cs` |
| `Sup_RF_URGHalfYearMaintain` |  | `Entity/Sup/QcForm/Year/Sup_RF_URGHalfYearMaintain.cs` |
| `Sup_RF_URGMonthMaintain` |  | `Entity/Sup/QcForm/Month/Sup_RF_URGMonthMaintain.cs` |
| `Sup_RF_URGQuarterMaintain` |  | `Entity/Sup/QcForm/Quarter/Sup_RF_URGQuarterMaintain.cs` |
| `Sup_RF_URGWeekMaintain` |  | `Entity/Sup/QcForm/Week/Sup_RF_URGWeekMaintain.cs` |
| `Sup_RF_URGYearMaintain` |  | `Entity/Sup/QcForm/Year/Sup_RF_URGYearMaintain.cs` |
| `Sup_RF_VOCQualityControlData` | VOC质控数据 | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCQualityControlData.cs` |
| `Sup_RF_VOCQualityControlDataDetail` | 校准曲线 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePoint.cs` |
| `Sup_RF_VOCsAMASamplingFlowRecord` | AMA-VOCs采样流量质控记录表（每月） | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsAMASamplingFlowRecord.cs` |
| `Sup_RF_VOCsChromatotecSamplingFlowRecord` | 科玛特-VOCs流量核查表（每月） | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsChromatotecSamplingFlowRecord.cs` |
| `Sup_RF_VOCsEXPECMulityPointCurveRecord` | 谱育EXPEC-VOCs多点曲线质控记录表（每季度） | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsEXPECMulityPointCurveRecord.cs` |
| `Sup_RF_VOCsEXPECMulityPointCurveRecord_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsEXPECMulityPointCurveRecord.cs` |
| `Sup_RF_VOCsEXPECMulityPointCurveRecord_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsEXPECMulityPointCurveRecord.cs` |
| `Sup_RF_VOCsEXPECSamplingFlowRecord` | 谱育EXPEC-VOCs采样流量质控记录表(每月） | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsEXPECSamplingFlowRecord.cs` |
| `Sup_RF_VOCsMulityPointCurveRecord` | AMA-VOCs多点曲线校准记录表（每月） | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsMulityPointCurveRecord.cs` |
| `Sup_RF_VOCsMulityPointCurveRecord_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsMulityPointCurveRecord.cs` |
| `Sup_RF_VOCsMulityPointCurveRecord_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsMulityPointCurveRecord.cs` |
| `Sup_RF_VOCsSinglePointCheckQC` | 科玛特-VOCs单点核查质控记录表（每周） | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsSinglePointCheckQC.cs` |
| `Sup_RF_VOCsSinglePointCheckQC_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsSinglePointCheckQC.cs` |
| `Sup_RF_VOCsSinglePointCheckQC_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsSinglePointCheckQC.cs` |
| `Sup_RF_VOCsWHTHMulityPointCurveRecord` | 武汉天虹VOCs多点曲线校准记录表（每月） | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsWHTHMulityPointCurveRecord.cs` |
| `Sup_RF_VOCsWHTHMulityPointCurveRecord_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsWHTHMulityPointCurveRecord.cs` |
| `Sup_RF_VOCsWHTHMulityPointCurveRecord_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsWHTHMulityPointCurveRecord.cs` |
| `Sup_RF_VOCsWHTHSamplingFlowRecord` | 武汉天虹-VOCs流量核查记录表（每月） | `Entity/Sup/QcForm/VOCs/Sup_RF_VOCsWHTHSamplingFlowRecord.cs` |
| `Sup_RF_VisibilityMeter` |  | `Entity/Sup/QcForm/Week/Sup_RF_VisibilityMeter.cs` |
| `Sup_RF_VoCsChromatotecCheck` | 科玛特-例行巡检记录表（每周） | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsChromatotecCheck.cs` |
| `Sup_RF_VoCsChromatotecDetectionLimitRecord` | 科玛特-VOCs工作曲线校准和方法检出限记录表（季度） | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsChromatotecDetectionLimitRecord.cs` |
| `Sup_RF_VoCsChromatotecDetectionLimitRecord_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsChromatotecDetectionLimitRecord.cs` |
| `Sup_RF_VoCsChromatotecDetectionLimitRecord_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsChromatotecDetectionLimitRecord.cs` |
| `Sup_RF_VoCsDetectionLimitRecord` | AMA-VOCs方法检出限记录表（每月） | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsDetectionLimitRecord.cs` |
| `Sup_RF_VoCsDetectionLimitRecord_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsDetectionLimitRecord.cs` |
| `Sup_RF_VoCsDetectionLimitRecord_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsDetectionLimitRecord.cs` |
| `Sup_RF_VoCsEXPECCheck` | 谱育EXPEC-VOCs例行巡检记录表（每周） | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsEXPECCheck.cs` |
| `Sup_RF_VoCsEXPECDetectionLimitRecord` | 谱育EXPEC-VOCs方法检出限记录表（每季度） | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsEXPECDetectionLimitRecord.cs` |
| `Sup_RF_VoCsEXPECDetectionLimitRecord_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsEXPECDetectionLimitRecord.cs` |
| `Sup_RF_VoCsEXPECDetectionLimitRecord_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsEXPECDetectionLimitRecord.cs` |
| `Sup_RF_VoCsTianHongCheck` | 武汉天虹VOC例行巡检记录表（每周） | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsTianHongCheck.cs` |
| `Sup_RF_VoCsWHTHDetectionLimitRecord` | 武汉天虹-VOCs方法检出限记录表（每月） | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsWHTHDetectionLimitRecord.cs` |
| `Sup_RF_VoCsWHTHDetectionLimitRecord_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsWHTHDetectionLimitRecord.cs` |
| `Sup_RF_VoCsWHTHDetectionLimitRecord_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VoCsWHTHDetectionLimitRecord.cs` |
| `Sup_RF_VocsBlankCheck` | VOCs（广州禾信）空白检测记录表 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsBlankCheck.cs` |
| `Sup_RF_VocsBlankCheck_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsBlankCheck.cs` |
| `Sup_RF_VocsBlankCheck_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsBlankCheck.cs` |
| `Sup_RF_VocsCurveDetectionLimit` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsCurveDetectionLimit.cs` |
| `Sup_RF_VocsCurveDetectionLimit_Record` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsCurveDetectionLimit.cs` |
| `Sup_RF_VocsFlowCheck` | VOCs（广州禾信）标准曲线校准记录表 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsFlowCheck.cs` |
| `Sup_RF_VocsInternalStandard` | VOCs（广州禾信）单点质控记录表 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsInternalStandard.cs` |
| `Sup_RF_VocsInternalStandard_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsInternalStandard.cs` |
| `Sup_RF_VocsMulityPointCheck` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsMulityPointCheck.cs` |
| `Sup_RF_VocsMulityPointCheck_Record` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsMulityPointCheck.cs` |
| `Sup_RF_VocsSceneCheck` | VOCs（广州禾信）周巡检记录 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSceneCheck.cs` |
| `Sup_RF_VocsSinglePoint` | VOCs（广州禾信）单点质控记录表 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePoint.cs` |
| `Sup_RF_VocsSinglePointCheck` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePointCheck.cs` |
| `Sup_RF_VocsSinglePointCheck_Config` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePointCheck.cs` |
| `Sup_RF_VocsSinglePointCheck_Record` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePointCheck.cs` |
| `Sup_RF_VocsSinglePoint_Data` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePoint.cs` |
| `Sup_RF_VocsStandardCurveCalibrate` | VOCs（广州禾信）标准曲线校准记录表 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsStandardCurveCalibrate.cs` |
| `Sup_RF_WaterSoluble` |  | `Entity/Sup/QcForm/Week/Sup_RF_WaterSoluble.cs` |
| `Sup_RF_WaterSolubleIonsBlankCheck` | 空白核查 | `Entity/Sup/QcForm/Week/Sup_RF_WaterSolubleIonsQuality.cs` |
| `Sup_RF_WaterSolubleIonsBlankCheckVM` |  | `Entity/Sup/QcForm/Week/Sup_RF_WaterSolubleIonsQuality.cs` |
| `Sup_RF_WaterSolubleIonsCalibration` | 校准曲线 | `Entity/Sup/QcForm/Week/Sup_RF_WaterSolubleIonsQuality.cs` |
| `Sup_RF_WaterSolubleIonsCalibrationVM` |  | `Entity/Sup/QcForm/Week/Sup_RF_WaterSolubleIonsQuality.cs` |
| `Sup_RF_WaterSolubleIonsFlowCheckVM` |  | `Entity/Sup/QcForm/Week/Sup_RF_WaterSolubleIonsQuality.cs` |
| `Sup_RF_WaterSolubleIonsQuality` | 气溶胶水溶性离子质控记录表 | `Entity/Sup/QcForm/Week/Sup_RF_WaterSolubleIonsQuality.cs` |
| `Sup_RF_WaterSolubleIonsSingleCheck` | 单点核查 | `Entity/Sup/QcForm/Week/Sup_RF_WaterSolubleIonsQuality.cs` |
| `Sup_RF_WaterSolubleIonsSingleCheckVM` |  | `Entity/Sup/QcForm/Week/Sup_RF_WaterSolubleIonsQuality.cs` |
| `Sup_RF_WaterSolubleIonsSystemBlank` | 系统空白 | `Entity/Sup/QcForm/Week/Sup_RF_WaterSolubleIonsQuality.cs` |
| `Sup_RF_WaterSolubleMultipoint` |  | `Entity/Sup/QcForm/Month/Sup_RF_WaterSolubleMultipoint.cs` |
| `Sup_RF_WeekSecurityCheck` | 站房安全管理检查表 每个站点只做一次，目前绑定到 每个站点都有的光解速率仪上 | `Entity/Sup/QcForm/Week/Sup_RF_WeekSecurityCheck.cs` |
| `Sup_RF_Week_BJCCheck` |  | `Entity/Sup/QcForm/Week/Sup_RF_Week_BJCCheck.cs` |
| `Sup_RF_Week_FKXLiDAR` |  | `Entity/Sup/QcForm/Week/Sup_RF_Week_FKXLiDAR.cs` |
| `Sup_RF_Week_HONOCheck` | HONO监测仪 周巡检表 | `Entity/Sup/QcForm/Week/Sup_RF_Week_HONOCheck.cs` |
| `Sup_RF_Week_HONOQC` | HONO监测仪 周质控表 | `Entity/Sup/QcForm/Week/Sup_RF_Week_HONOQC.cs` |
| `Sup_RF_Week_NMHCQC` | 甲烷非甲烷总烃分析仪 周质控表 | `Entity/Sup/QcForm/Week/Sup_RF_Week_NMHCQC.cs` |
| `Sup_RF_Week_RadiationRecord` |  | `Entity/Sup/QcForm/Week/Sup_RF_Week_RadiationRecord.cs` |
| `Sup_RF_Week_THLiDAR` |  | `Entity/Sup/QcForm/Week/Sup_RF_Week_THLiDAR.cs` |
| `Sup_RF_Week_TrafficFlowCheck` | 车流量监测仪 周检查表 | `Entity/Sup/QcForm/Week/Sup_RF_Week_TrafficFlowCheck.cs` |
| `Sup_RF_Week_YT_Check` | Sup_RF_Week_YT_Check 甲烷非甲烷总烃在线分析仪周巡检记录表 优泰 | `Entity/Sup/QcForm/Week/Sup_RF_Week_YT_Check.cs` |
| `Sup_RF_Week_YT_RepairRecord` | Sup_RF_Week_YT_RepairRecord 甲烷非甲烷总烃在线分析仪维修记录表 优泰 | `Entity/Sup/QcForm/Week/Sup_RF_Week_YT_RepairRecord.cs` |
| `Sup_RF_Week_YT_SingleQC` | Sup_RF_Week_YT_SingleQC 甲烷非甲烷总烃在线分析仪空白-单点质控记录表 优泰 | `Entity/Sup/QcForm/Week/Sup_RF_Week_YT_SingleQC.cs` |
| `Sup_RF_WholeDiaphargmCalibration` | 天瑞-重金属全膜校准记录表（每年） | `Entity/Sup/QcForm/Year/Sup_RF_WholeDiaphargmCalibration.cs` |
| `Sup_RF_WholeDiaphragm` | 数据表实体类：Sup_RF_WholeDiaphragm | `Entity/Sup/QcForm/Sup_RF_WholeDiaphragm.cs` |
| `Sup_RF_WorkingCurve` |  | `Entity/Sup/QcForm/Month/Sup_RF_WorkingCurve.cs` |
| `Sup_RF_YearNepheloMeterCheck` | 数据表实体类：Sup_RF_YearNepheloMeterCheck | `Entity/Sup/QcForm/NepheloMeter/Sup_RF_YearNepheloMeterCheck.cs` |
| `Sup_RF_Year_HONOCheck` | HONO监测仪 年巡检表 | `Entity/Sup/QcForm/Year/Sup_RF_Year_HONOCheck.cs` |
| `Sup_RF_Year_RadiationCalibration` |  | `Entity/Sup/QcForm/Week/Sup_RF_Year_RadiationCalibration.cs` |
| `Sup_RF_Year_RadiationCalibration_Bmet` |  | `Entity/Sup/QcForm/Year/Sup_RF_Year_RadiationCalibration_Bmet.cs` |
| `Sup_RF_Year_YT_AccuracyRecord` | Sup_RF_Year_YT_AccuracyRecord 甲烷非甲烷总烃在线分析仪精密度、准确度记录表 优泰 | `Entity/Sup/QcForm/Year/Sup_RF_Year_YT_AccuracyRecord.cs` |
| `Sup_RF_ZeroCalibration` |  | `Entity/Sup/QcForm/Week/Sup_RF_ZeroCalibration.cs` |
| `Sup_RF_ZeroSpanCalibration` |  | `Entity/Sup/QcForm/Week/Sup_RF_ZeroSpanCalibration.cs` |
| `Sup_RF_thybDayMaintain` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_thybDayMaintain.cs` |
| `Sup_RF_thybDayMaintain_Record` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_thybDayMaintain.cs` |
| `Sup_RF_thybFlowCheck` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_thybFlowCheck.cs` |
| `Sup_RF_thybHalfYearMaintain` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_thybHalfYearMaintain.cs` |
| `Sup_RF_thybMonthMaintain` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_thybMonthMaintain.cs` |
| `Sup_RF_thybQuarterMaintain` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_thybQuarterMaintain.cs` |
| `Sup_RF_thybWeekCheck` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_thybWeekCheck.cs` |
| `Sup_RF_thybYearMaintain` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_thybYearMaintain.cs` |
| `Sup_ReferenceMaterial` | 标准物质 | `Entity/Sup/QCDevice/Sup_ReferenceMaterial.cs` |
| `Sup_SEC_Vocs_Config` |  | `Entity/Sup/OPA/Sup_ScoreSheet.cs` |
| `Sup_SEC_Vocs_Data` |  | `Entity/Sup/OPA/Sup_ScoreSheet.cs` |
| `Sup_ScoreSheet` |  | `Entity/Sup/OPA/Sup_ScoreSheet.cs` |
| `Sup_SpecialDeviceConfig` |  | `Entity/Sup/Sup_SpecialDeviceConfig.cs` |
| `Sup_Station` |  | `Entity/Sup/Sup_Station.cs` |
| `Sup_UserDevice` | 设备 | `Entity/Sup/Sup_UserDevice.cs` |
| `Sup_VOCs_CurveVerificationPoint` | 曲线验证点 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePoint.cs` |
| `Sup_VOCs_DetectionItem` |  | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePoint.cs` |
| `Sup_VOCs_InternalStandard` | 内标响应 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePoint.cs` |
| `Sup_VOCs_SystemBlank` | 系统空白 | `Entity/Sup/QcForm/VOCs/Sup_RF_VocsSinglePoint.cs` |

## 主网报表实体（ReportForms 类标题）

| 类/表 | 表单标题 | 文件 |
| --- | --- | --- |
| `PW_TASK` | 数据表实体类：PW_TASK | `Entity/ReportForms/PW_TASK.cs` |
| `PW_TASKITEM` | 数据表实体类：PW_TASKITEM | `Entity/ReportForms/PW_TASKITEM.cs` |
| `PW_TASKITEMTEMP` |  | `Entity/ReportForms/PW_TASKITEM.cs` |
| `PW_TASKTEMP` | 数据表实体类：PW_TASKTEMP | `Entity/ReportForms/PW_TASK.cs` |
| `PW_UNITPLAN` |  | `Entity/ReportForms/PW_TASK.cs` |
| `RF_BCMonitorInspection` | 数据表实体类：RF_BCMonitorInspection | `Entity/ReportForms/RF_BCMonitorInspection.cs` |
| `RF_CUSTOMITEM` | 数据表实体类：RF_CUSTOMITEM | `Entity/ReportForms/RF_CUSTOMITEM.cs` |
| `RF_HY_EnvironmentHumidity` | Beta射线法颗粒物连续监测仪环境湿度校准表 | `Entity/ReportForms/RF_Q_GaseousFlowCheck.cs` |
| `RF_HY_GASEOUSCALIDEVICECHECK` | 数据表实体类：RF_HY_GASEOUSCALIDEVICECHECK | `Entity/ReportForms/RF_HY_GASEOUSCALIDEVICECHECK.cs` |
| `RF_HY_Humidity` | 仪器内部湿度传感器 | `Entity/ReportForms/RF_Q_GaseousFlowCheck.cs` |
| `RF_HY_NOXCONVERSIONRATE` | 数据表实体类：RF_HY_NOXCONVERSIONRATE | `Entity/ReportForms/RF_HY_NOXCONVERSIONRATE.cs` |
| `RF_HY_O3VALUEPASS` | 数据表实体类：RF_HY_O3VALUEPASS | `Entity/ReportForms/RF_HY_O3VALUEPASS.cs` |
| `RF_HY_STATIONDEVICEMAINTAIN` | 数据表实体类：RF_HY_STATIONDEVICEMAINTAIN | `Entity/ReportForms/RF_HY_STATIONDEVICEMAINTAIN.cs` |
| `RF_HY_StationMaintainCheck` | 数据表实体类：陕西省省控空气自动站运行维护记录表（每季） | `Entity/ReportForms/RF_HY_StationMaintainCheck.cs` |
| `RF_HY_VISIBILITYCALI` | 数据表实体类：RF_HY_VISIBILITYCALI | `Entity/ReportForms/RF_HY_VISIBILITYCALI.cs` |
| `RF_ITEM` | 数据表实体类：RF_ITEM | `Entity/ReportForms/RF_W_ITEM.cs` |
| `RF_Item_And_Supply` |  | `Entity/ReportForms/RF_Item_And_Supply.cs` |
| `RF_M_GASEOUSCALIDEVICECHECK` | 数据表实体类：RF_HY_GASEOUSCALIDEVICECHECK | `Entity/ReportForms/RF_HY_GASEOUSCALIDEVICECHECK.cs` |
| `RF_M_GaseousCaliCheck` | 数据表实体类：RF_M_GASEOUSCALICHECK | `Entity/ReportForms/RF_M_GaseousCaliCheck.cs` |
| `RF_M_GaseousFlowCheck` | 数据表实体类：RF_M_GASEOUSFLOWCHECK | `Entity/ReportForms/RF_M_GaseousFlowCheck.cs` |
| `RF_M_GaseousFlowCheckDetail` | 数据表实体类：RF_M_GASEOUSFLOWCHECKDETAIL | `Entity/ReportForms/RF_M_GaseousFlowCheckDetail.cs` |
| `RF_M_MANUALCOMPARISON` | 数据表实体类：RF_M_MANUALCOMPARISON | `Entity/ReportForms/RF_M_MANUALCOMPARISON.cs` |
| `RF_M_MANUALCOMPARISONDETAIL` | 数据表实体类：RF_M_MANUALCOMPARISONDETAIL | `Entity/ReportForms/RF_M_MANUALCOMPARISONDETAIL.cs` |
| `RF_M_MEMBRANEWEIGHING` | 数据表实体类：RF_M_MEMBRANEWEIGHING | `Entity/ReportForms/RF_M_MEMBRANEWEIGHING.cs` |
| `RF_M_PMDeviceMaintain` | 数据表实体类：RF_M_PMDeviceMaintain | `Entity/ReportForms/RF_M_PMDeviceMaintain.cs` |
| `RF_M_StationDeviceMaintain` | 数据表实体类：RF_M_STATIONDEVICEMAINTAIN | `Entity/ReportForms/RF_M_StationDeviceMaintain.cs` |
| `RF_M_StationMaintainCheck` | 数据表实体类：（表3-1）运行维护记录表（月） | `Entity/ReportForms/RF_M_StationMaintainCheck.cs` |
| `RF_PM1MonitorInspection` | 数据表实体类：RF_PM1MonitorInspection | `Entity/ReportForms/RF_PM1MonitorInspection.cs` |
| `RF_Q_GASEOUSPRECISION_CO` | 数据表实体类：RF_Q_GASEOUSPRECISION_CO | `Entity/ReportForms/RF_Q_GASEOUSPRECISION_CO.cs` |
| `RF_Q_GASEOUSPRECISION_NO2` | 数据表实体类：RF_Q_GASEOUSPRECISION_NO2 | `Entity/ReportForms/RF_Q_GASEOUSPRECISION_NO2.cs` |
| `RF_Q_GASEOUSPRECISION_O3` | 数据表实体类：RF_Q_GASEOUSPRECISION_O3 | `Entity/ReportForms/RF_Q_GASEOUSPRECISION_O3.cs` |
| `RF_Q_GASEOUSPRECISION_SO2` | 数据表实体类：RF_Q_GASEOUSPRECISION_SO2 | `Entity/ReportForms/RF_Q_GASEOUSPRECISION_SO2.cs` |
| `RF_Q_GaseousFlowCheck` | 动态气体校准仪流量检查表 | `Entity/ReportForms/RF_Q_GaseousFlowCheck.cs` |
| `RF_Q_GaseousMultipoint_CO` | 数据表实体类：RF_Q_GASEOUSMULTIPOINT_CO | `Entity/ReportForms/RF_Q_GASEOUSMULTIPOINT_CO.cs` |
| `RF_Q_GaseousMultipoint_NO2` | 数据表实体类：RF_Q_GASEOUSMULTIPOINT_NO2 | `Entity/ReportForms/RF_Q_GASEOUSMULTIPOINT_NO2.cs` |
| `RF_Q_GaseousMultipoint_O3` | 数据表实体类：RF_Q_GASEOUSMULTIPOINT_O3 | `Entity/ReportForms/RF_Q_GASEOUSMULTIPOINT_O3.cs` |
| `RF_Q_GaseousMultipoint_SO2` | 数据表实体类：RF_Q_GASEOUSMULTIPOINT_SO2 | `Entity/ReportForms/RF_Q_GASEOUSMULTIPOINT_SO2.cs` |
| `RF_Q_LONGOPTICALPATH_NO2` | 数据表实体类：RF_Q_LONGOPTICALPATH_NO2 | `Entity/ReportForms/RF_Q_LONGOPTICALPATH_NO2.cs` |
| `RF_Q_LONGOPTICALPATH_O3` | 数据表实体类：RF_Q_LONGOPTICALPATH_O3 | `Entity/ReportForms/RF_Q_LONGOPTICALPATH_O3.cs` |
| `RF_Q_LONGOPTICALPATH_SO2` | 数据表实体类：RF_Q_LONGOPTICALPATH_SO2 | `Entity/ReportForms/RF_Q_LONGOPTICALPATH_SO2.cs` |
| `RF_Q_PM10RUNSTATUSCHECK` | 数据表实体类：RF_Q_PM10RUNSTATUSCHECK | `Entity/ReportForms/RF_Q_PM10RUNSTATUSCHECK.cs` |
| `RF_Q_PM25RUNSTATUSCHECK` | 数据表实体类：RF_Q_PM25RUNSTATUSCHECK | `Entity/ReportForms/RF_Q_PM25RUNSTATUSCHECK.cs` |
| `RF_Q_PMPRESSURE` | 数据表实体类：RF_Q_PMPRESSURE | `Entity/ReportForms/RF_Q_PMPRESSURE.cs` |
| `RF_Q_PMRUNSTATUSCHECK` | 数据表实体类：RF_Q_PMRUNSTATUSCHECK | `Entity/ReportForms/RF_Q_PMRUNSTATUSCHECK.cs` |
| `RF_Q_StationDeviceClean` | 站点设备清洁记录（每季度） 数据表实体类：RF_Q_StationDeviceClean | `Entity/ReportForms/RF_Q_StationDeviceClean.cs` |
| `RF_Q_StationMaintainCheck` | 数据表实体类：陕西省省控空气自动站运行维护记录表（每季） | `Entity/ReportForms/RF_Q_StationMaintainCheck.cs` |
| `RF_RULE` | 数据表实体类：RF_RULE | `Entity/ReportForms/RF_RULE.cs` |
| `RF_RULEITEM` | 数据表实体类：RF_RULEITEM | `Entity/ReportForms/RF_RULEITEM.cs` |
| `RF_RULEITEM_RELEVANCE` | 数据表实体类：RF_RULEITEM_RELEVANCE | `Entity/ReportForms/RF_RULEITEM_RELEVANCE.cs` |
| `RF_RuleItemTask` |  | `Entity/ReportForms/RF_RuleItemTask.cs` |
| `RF_SEC_APPLICATIONFORM` | 数据表实体类：RF_SEC_APPLICATIONFORM | `Entity/ReportForms/RF_SEC_APPLICATIONFORM.cs` |
| `RF_SEC_GASEOUSCHECK` | 数据表实体类：联机比对关系表 2.3 气态检查表 | `Entity/ReportForms/RF_SEC_GASEOUSCHECK.cs` |
| `RF_SEC_INSTRUMENTRECORD` | 数据表实体类：RF_SEC_INSTRUMENTRECORD | `Entity/ReportForms/RF_SEC_INSTRUMENTRECORD.cs` |
| `RF_SEC_MONITORINGCHECK` | 数据表实体类：RF_SEC_MONITORINGCHECK | `Entity/ReportForms/RF_SEC_MONITORINGCHECK.cs` |
| `RF_SEC_STATIONPROPOSAL` | 数据表实体类：建议和意见表 | `Entity/ReportForms/RF_SEC_STATIONPROPOSAL.cs` |
| `RF_TW_CleanCuttingHead` |  | `Entity/ReportForms/RF_TW_CleanCuttingHead.cs` |
| `RF_TW_PmFlowCalibrate` |  | `Entity/ReportForms/RF_TW_PmFlowCalibrate.cs` |
| `RF_TW_PmFlowCheck` |  | `Entity/ReportForms/RF_TW_PmFlowCheck.cs` |
| `RF_W_GASEOUSCHECK_CO` | 数据表实体类：RF_W_GASEOUSCHECK_O3 | `Entity/ReportForms/RF_W_GASEOUSCHECK_CO.cs` |
| `RF_W_GASEOUSCHECK_NOX` | 数据表实体类：RF_W_GASEOUSCHECK_NOX | `Entity/ReportForms/RF_W_GASEOUSCHECK_NOX.cs` |
| `RF_W_GASEOUSCHECK_O3` | 数据表实体类：RF_W_GASEOUSCHECK_O3 | `Entity/ReportForms/RF_W_GASEOUSCHECK_O3.cs` |
| `RF_W_GASEOUSCHECK_SO2` | 数据表实体类：RF_W_GASEOUSCHECK_SO2 | `Entity/ReportForms/RF_W_GASEOUSCHECK_SO2.cs` |
| `RF_W_GrainCalibrationCheckAttach` | 数据表实体类：陕西省省控空气自动站颗粒监测仪校准检查表 附件表 | `Entity/ReportForms/RF_W_GrainCalibrationCheck.cs` |
| `RF_W_GrainCalibrationCheck_PM10` | 数据表实体类：陕西省省控空气自动站颗粒监测仪校准检查表 | `Entity/ReportForms/RF_W_GrainCalibrationCheck.cs` |
| `RF_W_GrainCalibrationCheck_PM25` | 数据表实体类：陕西省省控空气自动站颗粒监测仪校准检查表 | `Entity/ReportForms/RF_W_GrainCalibrationCheck.cs` |
| `RF_W_INSPECTIONSUMMARY` | 数据表实体类：RF_W_INSPECTIONSUMMARY | `Entity/ReportForms/RF_W_INSPECTIONSUMMARY.cs` |
| `RF_W_Inspection` | 数据表实体类：RF_W_INSPECTION | `Entity/ReportForms/RF_W_Inspection.cs` |
| `RF_W_LONGOPTICALPATH` | 数据表实体类：RF_W_LONGOPTICALPATH | `Entity/ReportForms/RF_W_LONGOPTICALPATH.cs` |
| `RF_W_OtherDeviceCheck` | 数据表实体类：RF_W_OTHERDEVICECHECK | `Entity/ReportForms/RF_W_OtherDeviceCheck.cs` |
| `RF_W_PmCheck` | 颗粒物PM10,PM2.5自动监测分析仪运行状况检查记录表实体类：RF_W_PMCHECK | `Entity/ReportForms/RF_W_PmCheck.cs` |
| `RF_Y_DEVICECHANGE` | 数据表实体类：RF_Y_DEVICECHANGE | `Entity/ReportForms/RF_Y_DEVICECHANGE.cs` |
| `RF_Y_DEVICEREPAIR` | 数据表实体类：RF_Y_DEVICEREPAIR | `Entity/ReportForms/RF_Y_DEVICEREPAIR.cs` |
| `RF_Y_PreventiveMaintenance` |  | `Entity/ReportForms/RF_Y_PreventiveMaintenance.cs` |
