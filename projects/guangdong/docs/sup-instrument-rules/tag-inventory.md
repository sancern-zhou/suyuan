# 组分站表单 tag 盘点（自动生成）

- 生成脚本：`backend/scripts/sup_tag_inventory.py`；扫描 guangdong_mart 全部 sup_rf% 分表。
- 填充率=非空且非业务占位（/、-、无等）的行占比；仅列出 ≥15% 的列，每 tag 最多 40 列。
- 用途：sup_form_profiles.yaml 建档清单依据；对照表单标题见同目录各转录分册。

## sup_rf_ambienttemperature（总行数 495，tag 数 1）

| ruleitemtag | 总行数 | 近90天 | 检查日期范围 | 监测项目 |
| --- | ---: | ---: | --- | --- |
| Sup_RF_AmbientTemperature | 495 | 175 | 2025-12-17 ~ 2026-10-27 | PM1×177、HeavyMetal×94、WaterSolubleIons×83、OCEC×77、CO2×27 |

### sup_rf_ambienttemperature / Sup_RF_AmbientTemperature

填充列：devicebrand(100%)，devicecode(100%)，devicemodel(100%)，p_iscalibrated(100%)，p_nextdate(100%)，p_prevdate(100%)，p_r_nextvalue(100%)，p_r_prevvalue(100%)，p_r_standard(100%)，t_iscalibrated(100%)，t_nextdate(100%)，t_prevdate(100%)，t_r_nextvalue(100%)，t_r_prevvalue(100%)，t_r_standard(100%)，t_model(91%)，p_code(91%)，p_model(91%)，t_code(91%)，remark(34%)，sensor(16%)

  - 样本 CH2610271793088956511 (2026-10-27 00:00:00): pollutanttype=OCEC；devicebrand=Sunset；devicemodel=Model 4L；devicecode=SC00073-4；t_model=DSR-THP；t_code=THP1801222893UA；t_prevdate=2026-04-27 00:00:00；t_nextdate=2027-04-26 00:00:00；t_r_standard=33.8；t_r_prevvalue=33.3；t_r_nextvalue=33.3；p_model=DSR-THP；p_code=THP1801222893UA；p_prevdate=2026-04-27 00:00:00；p_nextdate=2027-04-26 00:00:00；p_r_standard=101.21；p_r_prevvalue=101.14；p_r_nextvalue=101.14；t_iscalibrated=0；p_iscalibrated=0

## sup_rf_common（总行数 41001，tag 数 94）

| ruleitemtag | 总行数 | 近90天 | 检查日期范围 | 监测项目 |
| --- | ---: | ---: | --- | --- |
| Sup_RF_VocsSinglePoint | 6190 | 356 | 2021-10-15 ~ 2026-10-26 | VOCs×6190 |
| Sup_RF_Week_NMHCQC | 5639 | 489 | 2024-04-03 ~ 2026-10-30 | NMHC×5639 |
| Sup_RF_HP_DalyHealth | 5373 | 650 | 2023-03-18 ~ 2026-10-27 | CO2/CH4/CO/N2O×5373 |
| Sup_RF_WeekSecurityCheck | 4156 | 586 | 2024-05-11 ~ 2026-10-27 | ZF×4079、PDLI×47、NMHC×27、VOCs×3 |
| Sup_RF_PRInspectionRecord | 2644 | 91 | 2021-06-12 ~ 2026-10-26 | PDLI×2644 |
| Sup_RF_WaterSolubleIonsQuality | 2427 | 140 | 2022-04-29 ~ 2026-10-27 | WaterSolubleIons×2427 |
| Sup_RF_PANsWeekCheck | 2224 | 109 | 2021-09-27 ~ 2026-10-26 | PANs×2224 |
| Sup_RF_OCECJGWeekCheck | 1363 | 50 | 2021-10-14 ~ 2026-10-26 | OCEC×1363 |
| Sup_RF_VocsSceneCheck | 1083 | 59 | 2021-10-13 ~ 2026-10-21 | VOCs×1083 |
| Sup_RF_PDLIYearCheck | 955 | 81 | 2022-09-01 ~ 2026-10-21 | PM1×187、NMHC×129、BC×122、PDLI×100、VOCs×80 |
| Sup_RF_VocsFlowCheck | 936 | 82 | 2021-10-15 ~ 2026-10-28 | VOCs×936 |
| Sup_RF_HP_StationCheck | 795 | 88 | 2023-03-13 ~ 2026-10-22 | CO2/CH4/CO/N2O×795 |
| Sup_RF_HeavyMetalQuality | 661 | 63 | 2022-06-28 ~ 2026-10-21 | HeavyMetal×661 |
| Sup_RF_MSRoutineCheck | 600 | 21 | 2021-10-12 ~ 2026-10-23 | SingleParticle×600 |
| Sup_RF_PANsWorkCurveCalibration | 549 | 30 | 2021-10-15 ~ 2026-10-19 | PANs×549 |
| Sup_RF_Week_HONOCheck | 531 | 71 | 2023-12-21 ~ 2026-10-27 | HONO×531 |
| Sup_RF_TSIRoutineCheck | 413 | 0 | 2021-11-16 ~ 2025-12-31 | ParticleMeter-C×373、ParticleMeter-F×20、ParticleMeter-L×20 |
| Sup_RF_Week_HONOQC | 352 | 70 | 2024-04-25 ~ 2026-10-27 | HONO×352 |
| Sup_RF_Week_YT_SingleQC | 271 | 32 | 2024-07-02 ~ 2026-10-24 | NMHC×271 |
| Sup_RF_Week_YT_Check | 270 | 33 | 2024-07-02 ~ 2026-10-24 | NMHC×270 |
| Sup_RF_RULEITEMVOCs | 260 | 9 | 2021-11-01 ~ 2026-10-21 | VOCs×260 |
| RF_D_GreenHouseCheck | 246 | 90 | 2026-01-04 ~ 2026-10-27 | TDL×242、CO2/CH4/CO/N2O×4 |
| Sup_RF_HY_NMHCMaintenanceRecord | 177 | 25 | 2024-05-14 ~ 2026-10-23 | NMHC×177 |
| Sup_RF_VoCsEXPECCheck | 160 | 0 | 2021-10-13 ~ 2026-01-27 | VOCs×160 |
| Sup_RF_NMHCAnalyzerRecord | 156 | 12 | 2022-12-18 ~ 2026-10-14 | NMHC×156 |
| Sup_RF_PANsFlowCheck | 149 | 15 | 2023-11-29 ~ 2026-10-15 | PANs×149 |
| Sup_RF_Attex_Check | 147 | 0 | 2023-03-01 ~ 2025-12-31 | WenKuoLineLidar×147 |
| Sup_RF_OCECJGMultipointCheck | 131 | 6 | 2021-10-17 ~ 2026-09-28 | OCEC×131 |
| Sup_RF_HCHOCollectPercent | 128 | 0 | 2021-11-05 ~ 2024-03-30 | HCHO×128 |
| Sup_RF_HCHOMLinearError | 128 | 0 | 2021-10-31 ~ 2024-03-27 | HCHO×128 |
| Sup_RF_HCHODetectionLimit | 128 | 0 | 2021-10-16 ~ 2024-03-27 | HCHO×128 |
| Sup_RF_HCHORepeatTest | 128 | 0 | 2021-11-05 ~ 2024-03-27 | HCHO×128 |
| Sup_RF_Month_HONOCheck | 97 | 19 | 2024-01-10 ~ 2026-10-22 | HONO×97 |
| Sup_RF_Week_TrafficFlowCheck | 95 | 0 | 2024-03-20 ~ 2025-12-31 | TrafficFlow×95 |
| Sup_RF_TSIFlowCheckRecord | 90 | 0 | 2021-11-16 ~ 2025-12-19 | ParticleMeter-C×80、ParticleMeter-F×5、ParticleMeter-L×5 |
| Sup_RF_Month_HONOTest | 73 | 13 | 2025-02-20 ~ 2026-10-22 | HONO×73 |
| Sup_RF_PTR_MSQuality | 73 | 13 | 2023-04-13 ~ 2026-10-23 | PTR-MS×73 |
| Sup_RF_OCECJGSingleCheck | 69 | 0 | 2021-10-16 ~ 2022-06-16 | OCEC×69 |
| Sup_RF_Month_YT_FlowCalibration | 67 | 8 | 2024-07-02 ~ 2026-10-17 | NMHC×67 |
| Sup_RF_VoCsChromatotecCheck | 66 | 0 | 2021-10-16 ~ 2022-06-08 | VOCs×66 |
| Sup_RF_Month_YT_LeakChecking | 64 | 7 | 2024-09-01 ~ 2026-10-17 | NMHC×64 |
| Sup_RF_VOCsAMASamplingFlowRecord | 61 | 3 | 2021-11-01 ~ 2026-10-21 | VOCs×61 |
| Sup_RF_OcecEnvironmentCheck | 49 | 0 | 2021-10-12 ~ 2022-06-15 | OCEC×49 |
| Sup_RF_OcecFlowVerificationCheck | 46 | 3 | 2022-05-12 ~ 2026-10-21 | OCEC×46 |
| Sup_RF_MSQualityCalibration | 44 | 2 | 2021-11-09 ~ 2026-09-17 | SingleParticle×44 |
| Sup_RF_MSParticleSizeCalibration | 43 | 2 | 2021-11-09 ~ 2026-09-17 | SingleParticle×43 |
| Sup_RF_PANsRepeatabilityCheck | 38 | 1 | 2021-11-02 ~ 2026-10-14 | PANs×38 |
| Sup_RF_VOCsEXPECSamplingFlowRecord | 38 | 0 | 2021-10-30 ~ 2026-01-15 | VOCs×38 |
| Sup_RF_Week_THLiDAR | 38 | 13 | 2026-02-10 ~ 2026-10-22 | WSKXLD×38 |
| Sup_RF_Week_BJCCheck | 37 | 13 | 2026-02-10 ~ 2026-10-22 | BJC×37 |
| Sup_RF_PANsStabilityCheck | 37 | 0 | 2021-11-02 ~ 2026-04-24 | PANs×37 |
| Sup_RF_OcecHeliumMethaneCheck | 37 | 4 | 2021-12-17 ~ 2026-10-21 | OCEC×37 |
| RF_W_GreenHouseCheck | 35 | 12 | 2026-03-03 ~ 2026-10-20 | TDL×35 |
| Sup_RF_VoCsTianHongCheck | 31 | 0 | 2021-10-12 ~ 2022-06-12 | VOCs×31 |
| Sup_RF_Quarter_YT_NMHCRecord | 29 | 5 | 2024-09-25 ~ 2026-10-24 | NMHC×29 |
| Sup_RF_OcecOrganicCarbonCheck | 27 | 0 | 2021-10-21 ~ 2022-06-15 | OCEC×27 |
| Sup_RF_TurbidiMeterRoutineCheck | 25 | 0 | 2021-10-12 ~ 2022-03-29 | NepheloMeter×25 |
| Sup_RF_TurbidiMeterCalibration | 24 | 0 | 2021-10-12 ~ 2022-03-29 | NepheloMeter×24 |
| Sup_RF_OCECSamplingFlowCheck | 23 | 0 | 2021-10-12 ~ 2022-06-16 | OCEC×23 |
| Sup_RF_HP_Precision | 20 | 2 | 2023-03-14 ~ 2026-04-09 | CO2/CH4/CO/N2O×20 |
| Sup_RF_HONOConsumablesReplace | 17 | 9 | 2024-05-29 ~ 2026-10-21 | HONO×17 |
| Sup_RF_HP_Comparability | 17 | 2 | 2023-03-14 ~ 2026-10-09 | CO2/CH4/CO/N2O×17 |
| Sup_RF_Week_FKXLiDAR | 17 | 13 | 2026-06-30 ~ 2026-10-22 | FKXLD×17 |
| Sup_RF_HP_Accuracy | 16 | 2 | 2023-03-14 ~ 2026-04-09 | CO2/CH4/CO/N2O×16 |
| Sup_RF_MSFlowCheck | 16 | 0 | 2021-10-19 ~ 2022-06-14 | SingleParticle×16 |
| Sup_RF_thybWeekCheck | 16 | 16 | 2026-08-18 ~ 2026-10-26 | VOCs×16 |
| Sup_RF_VOCsChromatotecSamplingFlowRecord | 15 | 0 | 2021-10-16 ~ 2022-03-20 | VOCs×15 |
| Sup_RF_PaperTapeRecord | 13 | 0 | 2021-11-24 ~ 2022-06-15 | HeavyMetal×13 |
| Sup_RF_VOCsWHTHSamplingFlowRecord | 12 | 0 | 2021-10-19 ~ 2022-06-16 | VOCs×12 |
| Sup_RF_DiaphragmCheck | 10 | 0 | 2021-12-07 ~ 2022-06-15 | HeavyMetal×10 |
| Sup_RF_HalfYear_HONOCheck | 10 | 0 | 2025-03-24 ~ 2026-06-26 | HONO×10 |
| Sup_RF_OCECWeekCheck | 10 | 10 | 2026-08-18 ~ 2026-10-21 | OCEC×10 |
| Sup_RF_HP_Calibration | 9 | 0 | 2023-04-04 ~ 2023-07-24 | CO2/CH4/CO/N2O×9 |
| Sup_RF_VoCsWHTHDetectionLimitRecord | 8 | 0 | 2021-10-22 ~ 2023-09-20 | VOCs×8 |
| Sup_RF_VOCsWHTHMulityPointCurveRecord | 8 | 0 | 2021-10-22 ~ 2023-09-20 | VOCs×8 |
| Sup_RF_Year_YT_AccuracyRecord | 6 | 1 | 2024-09-25 ~ 2026-09-16 | NMHC×6 |
| Sup_RF_VoCsChromatotecDetectionLimitRecord | 6 | 0 | 2021-12-18 ~ 2022-05-17 | VOCs×6 |
| Sup_RF_VOCsEXPECMulityPointCurveRecord | 6 | 0 | 2021-12-24 ~ 2022-03-16 | VOCs×6 |
| Sup_RF_VOCsSinglePointCheckQC | 6 | 0 | 2021-10-16 ~ 2022-04-20 | VOCs×6 |
| Sup_RF_VoCsEXPECDetectionLimitRecord | 4 | 0 | 2021-12-24 ~ 2022-02-14 | VOCs×4 |
| Sup_RF_Year_HONOCheck | 4 | 0 | 2025-03-24 ~ 2025-12-30 | HONO×4 |
| Sup_RF_Quarter_HONOCheck | 4 | 0 | 2024-03-25 ~ 2024-03-29 | HONO×4 |
| Sup_RF_TurbidiMeterSamplingCheck | 4 | 0 | 2021-11-16 ~ 2022-03-14 | NepheloMeter×4 |
| Sup_RF_VocsStandardCurveCalibrate | 4 | 0 | 2021-11-01 ~ 2021-12-30 | VOCs×4 |
| Sup_RF_QualityCheck | 3 | 0 | 2021-12-17 ~ 2022-03-13 | HeavyMetal×3 |
| Sup_RF_Month_THLiDAR | 3 | 2 | 2026-07-21 ~ 2026-09-24 | WSKXLD×3 |
| (空) | 2 | 0 | 2025-12-31 ~ 2026-01-01 | - |
| Sup_RF_VOCsMulityPointCurveRecord | 2 | 0 | 2022-02-23 ~ 2022-02-23 | VOCs×2 |
| Sup_RF_VoCsDetectionLimitRecord | 2 | 0 | 2022-02-23 ~ 2022-02-23 | VOCs×2 |
| Sup_RF_WholeDiaphargmCalibration | 1 | 0 | 2021-12-01 ~ 2021-12-01 | HeavyMetal×1 |
| Sup_RF_O3LidarRepair | 1 | 1 | None ~ None | O3Lidar×1 |
| Sup_RF_OCECSunsetFlowCalibration | 1 | 0 | 2021-12-17 ~ 2021-12-17 | OCEC×1 |
| Sup_RF_MTHNMHCAnalyzer | 1 | 0 | 2022-02-09 ~ 2022-02-09 | NMHC×1 |
| RF_HY_GreenHouseCheck | 1 | 0 | 2026-06-09 ~ 2026-06-09 | TDL×1 |

### sup_rf_common / Sup_RF_VocsSinglePoint

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，bool_31(55%)，bool_32(55%)，bool_33(55%)，bool_34(55%)，bool_35(55%)，bool_36(55%)

  - 样本 CH2610271793082724452 (2026-10-26 00:00:00): pollutanttype=VOCs；devicebrand=HeXin；devicemodel=ACGCMS1000；devicecode=ACGCMS1000G0059

### sup_rf_common / Sup_RF_Week_NMHCQC

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(99%)，string3(99%)，string2(99%)，time1(99%)，time2(99%)，string4(98%)

  - 样本 CH2610261792992741611 (2026-10-20 00:00:00): pollutanttype=NMHC；devicebrand=ZTE；devicemodel=ZE-CEM2000G；remark=周质控直接使用低浓度标气给仪器采样，没有使用动态校准仪，故校准仪信息空白；devicecode=G16171F9188F；string1=2303504024；string2=2.03；string3=0.678；string4=9.5MPa；string47=16.09；string48=29.25

### sup_rf_common / Sup_RF_HP_DalyHealth

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(99%)，string2(99%)，string3(99%)，string5(99%)，bool_31(76%)，bool_32(76%)

  - 样本 CH2610251792919555282 (2026-10-27 00:00:00): pollutanttype=CO2/CH4/CO/N2O；devicebrand=AR；devicemodel=AR1303；devicecode=AR130322092393；string1=45；string2=45；string3=140；string5=0.004%

### sup_rf_common / Sup_RF_WeekSecurityCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610271793085124313 (2026-10-27 00:00:00): pollutanttype=ZF；devicebrand=站房；devicemodel=站房；devicecode=440200052P；string12=27；string13=50；string20=220

### sup_rf_common / Sup_RF_PRInspectionRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(46%)，bool_31(41%)，bool_32(41%)，bool_33(41%)，bool_34(41%)，bool_35(41%)

  - 样本 CH2610261793004234467 (2026-10-26 00:00:00): pollutanttype=PDLI；devicebrand=Bmet；devicemodel=UF-CCD；devicecode=127740

### sup_rf_common / Sup_RF_WaterSolubleIonsQuality

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，bool_31(49%)，bool_32(49%)，bool_33(49%)，bool_34(49%)，bool_35(49%)，bool_36(49%)

  - 样本 CH2610261792992741611 (2026-10-26 00:00:00): pollutanttype=WaterSolubleIons；devicebrand=TH；devicemodel=TH-GAC-IC3000；devicecode=302008003

### sup_rf_common / Sup_RF_PANsWeekCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string13(100%)，string1(100%)，string19(100%)，string2(100%)，string3(100%)，string11(100%)

  - 样本 CH2610261792981500762 (2026-10-26 00:00:00): pollutanttype=PANs；devicebrand=DADI ENCON；devicemodel=AKPAN-9000；devicecode=D1631990001；string1=AKPAN-9000；string2=D1631990001；string3=AKPAN-600；string4=CED11970008；string5=44021016936；string6=2MPa；string7=44020008941；string8=5.5MPa；string9=156260946182；string10=9.2MPa；string11=163260310069；string12=1500psi；string13=4；string14=3.910；string15=3.910；string16=2.25；string17=2.25；string18=Y=1.31E-008X；string19=0.9999；string20=12

### sup_rf_common / Sup_RF_OCECJGWeekCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(99%)，string13(99%)，string15(99%)，string29(99%)，string31(99%)，string9(99%)

  - 样本 CH2610261793005332817 (2026-10-26 00:00:00): pollutanttype=OCEC；devicebrand=FPI；devicemodel=OCEC-100；devicecode=CEF11940006；string1=0；string3=0；string5=8；string7=72.3；string9=0；string11=0；string13=0；string15=0；string17=39.7；string19=500；string21=10450；string23=14200；string25=0；string27=103.5；string28=新型炉膛，仪器正常。；string29=80/60/80；string30=20/20/20；string31=0/20/0；string32=0/20/0；string33=850

### sup_rf_common / Sup_RF_VocsSceneCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(99%)，string2(99%)，remark12(55%)，bool_31(47%)，bool_32(47%)，bool_33(47%)

  - 样本 CH2610231792758599203 (2026-10-20 00:00:00): pollutanttype=VOCs；devicebrand=HeXin；devicemodel=ACGCMS1000；devicecode=AG0101G0046S；string1=24.11；string2=46.0

### sup_rf_common / Sup_RF_PDLIYearCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，time1(100%)，time2(100%)，bool_31(62%)，bool_32(62%)，bool_33(62%)，bool_34(62%)

  - 样本 CH2610211792579482706 (2026-10-21 00:00:00): pollutanttype=PM1；devicebrand=TE；devicemodel=5014i；remark=PM1监测仪年度维护；devicecode=CM23438009

### sup_rf_common / Sup_RF_VocsFlowCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string4(99%)，string5(99%)，string6(99%)，string7(99%)，string2(99%)，time1(99%)

  - 样本 CH2610261793004250700 (2026-10-26 00:00:00): pollutanttype=VOCs；devicebrand=TH；devicemodel=TH-300B；devicecode=A382601001；string1=24.9°/44.8%/100.2；string2=270826；string4=20；string5=20；string6=22.2；string7=0.2385

### sup_rf_common / Sup_RF_HP_StationCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，bool_31(76%)，bool_32(76%)，bool_33(76%)，bool_34(76%)，bool_35(76%)，bool_36(76%)

  - 样本 CH2610251792862427989 (2026-10-22 00:00:00): pollutanttype=CO2/CH4/CO/N2O；devicebrand=AR；devicemodel=AR1303；devicecode=AR130322092393

### sup_rf_common / Sup_RF_HeavyMetalQuality

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，bool_31(54%)，bool_32(54%)，bool_33(54%)，bool_34(54%)，bool_35(54%)，bool_36(54%)

  - 样本 CH2610211792571480849 (2026-10-21 16:33:15.353000): pollutanttype=HeavyMetal；devicebrand=CES；devicemodel=XactTM625；devicecode=AM2017004

### sup_rf_common / Sup_RF_MSRoutineCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，bool_31(46%)，bool_32(46%)，bool_33(46%)，bool_34(46%)，bool_35(46%)，bool_36(46%)

  - 样本 CH2610181792308956872 (2026-10-23 00:00:00): pollutanttype=SingleParticle；devicebrand=HeXin；devicemodel=SPAMS 0525；devicecode=SPAMS0535GZHJ-04-YF；string6=风冷激光器；string12=风冷激光器

### sup_rf_common / Sup_RF_PANsWorkCurveCalibration

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string11(100%)，string2(100%)，string3(100%)，string5(100%)，string7(100%)

  - 样本 CH2610251792899974189 (2026-10-19 00:00:00): pollutanttype=PANs；devicebrand=FPI；devicemodel=PANs-1000；devicecode=D1631930002；string1=PANS-1000；string2=D1631930002；string3=PANS-200；string4=001P1950033；string5=44021018697；string6=3；string7=44020005920；string8=6；string9=2205106037；string10=9.5；string11=L187609027；string12=11.5；string13=8.929；string14=8.93；string15=8.832；string16=8.989；string17=8.832；string18=0.069；string19=6.649；string20=6.132

### sup_rf_common / Sup_RF_Week_HONOCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string2(100%)，string3(100%)，string4(100%)，string5(100%)，time1(100%)

  - 样本 CH2610251792942008434 (2026-10-27 00:00:00): pollutanttype=HONO；devicebrand=wisdominc；devicemodel=LOPAP-03；devicecode=G17-3022；string1=HONO分析仪；string2=LOPAP-03；string3=朱伟林；string4=壹点环境；string5=东莞东城；string50=24.99；string51=13.37；string52=0.0200 mg/L

### sup_rf_common / Sup_RF_TSIRoutineCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，bool_31(37%)，bool_32(37%)，bool_33(37%)，bool_34(37%)，bool_35(37%)，bool_36(37%)

### sup_rf_common / Sup_RF_Week_HONOQC

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610251792942008434 (2026-10-27 00:00:00): pollutanttype=HONO；devicebrand=wisdominc；devicemodel=LOPAP-03；devicecode=G17-3022；string1=HONO分析仪；string2=LOPAP-03；string3=朱伟林；string4=壹点环境；string5=东莞东城；string6=1000；string7=0.37；string11=0.0000；string12=-0.1633；string13=-0.3329；string14=0.0748；string15=-0.2315；string21=0.9853；string22=0.5736；string23=-0.251；string24=0.5934；string25=-0.1742；string26=1360；string27=-4.426；string28=0.999938

### sup_rf_common / Sup_RF_Week_YT_SingleQC

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string11(100%)，string13(100%)，string17(100%)，string2(100%)，string3(100%)

  - 样本 CH2610271793044890609 (2026-10-24 00:00:00): pollutanttype=NMHC；devicebrand=优泰；devicemodel=NCMS6300；remark=合格；devicecode=060223003；string1=Ntrace.2207；string2=KM0410-62A-1-00-0-300；string3=NGZ5000；string4=CNEMC2025-003-L1371；string5=空气中甲烷，丙烷气体标准物质；string6=L194709003；string7=甲烷，丙烷；string8=28；string9=38；string10=101.2；string11=陈志文；string12=0；string13=2000；string14=2008.85；string15=0.44；string16=14.06；string17=500；string18=497.74；string19=-0.45

### sup_rf_common / Sup_RF_Week_YT_Check

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark10(100%)，remark11(100%)，remark12(100%)，remark13(100%)，remark8(100%)，remark9(100%)

  - 样本 CH2610261792967638008 (2026-10-24 00:00:00): pollutanttype=NMHC；devicebrand=优泰；devicemodel=NCMS6300；devicecode=060223003

### sup_rf_common / Sup_RF_RULEITEMVOCs

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string10(100%)，string11(100%)，string13(100%)，string15(100%)，string16(100%)，string19(100%)

  - 样本 CH2610211792552589309 (2026-10-21 00:00:00): pollutanttype=VOCs；devicebrand=AMA；devicemodel=GC5000；devicecode=151085300 /151086301；string2=33.3；string3=33.3；string5=0.70；string6=0.84；string8=交接遗留；string10=30；string11=15；string13=15；string15=179；string16=179；string17=±2℃；string19=3.0；string21=零气发生器压力设置3bar，高压会导致管路异常（交接遗留）；string24=氢气发生器原机故障，使用备机，备机压力设置4bar（交接遗留）

### sup_rf_common / RF_D_GreenHouseCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610271793086621808 (2026-10-27 00:00:00): pollutanttype=TDL；devicebrand=HY；devicemodel=LI-7500DS,LI-7500DS；devicecode=75D-5166,75D-5166；string1=LI-7500DS；string2=75D-5166；string3=LI-7500DS；string4=75D-5166；string5=LI-7500DS；string6=75D-5166；string10=√；string12=91.354；string14=0；string15=设备返厂维修；string16=23.815；string18=0；string20=254；string22=-6.499；string24=2.755；string26=0.652；string28=27.617；string30=√；string40=54.500；string42=55.001

### sup_rf_common / Sup_RF_HY_NMHCMaintenanceRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，bool_31(94%)，bool_32(94%)，bool_33(94%)，bool_34(94%)，bool_35(94%)，bool_36(94%)

  - 样本 CH2610261793007599149 (2026-10-23 00:00:00): pollutanttype=NMHC；devicebrand=ZTE；devicemodel=ZE-CEM2000G；devicecode=G16171F91885；string1=AAQM-N100；string2=00500215006；string3=1.009；string4=-0.01874；string5=1.00899；string6=0.16637

### sup_rf_common / Sup_RF_VoCsEXPECCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string11(100%)，string12(100%)，string14(100%)，string15(100%)，string17(100%)，string18(100%)

### sup_rf_common / Sup_RF_NMHCAnalyzerRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，time1(98%)，string8(95%)，string17(94%)，string10(94%)，string11(94%)，string12(94%)

  - 样本 CH2610151792024375601 (2026-10-14 00:00:00): pollutanttype=NMHC；devicebrand=ZTE；devicemodel=ZE-CEM2000G；devicecode=G16171F91853；string8=500；string9=485；string10=487；string11=488；string12=491；string13=490；string14=491；string15=491；string16=6.714；string17=1000；string18=911；string19=907；string20=906；string21=900；string22=902；string23=902；string24=903；string25=11.868；string26=800；string27=792

### sup_rf_common / Sup_RF_PANsFlowCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(97%)，string13(97%)，string14(97%)，string15(97%)，string16(97%)，string17(97%)

  - 样本 CH2610181792335599901 (2026-10-14 00:00:00): pollutanttype=PANs；devicebrand=DADI ENCON；devicemodel=AKPAN-9000；remark=W65修正公式，y=0.9916x+0.0063，单位L/min
W6；devicecode=D1631990003；string1=AKPAN-900；string2=D1631990003；string3=P300A-2-20SLPM；string4=P1XCF1218VAAW65；string5=P300A-2-100sccm；string6=P1XCF1218VAAW63；string7=数字温湿度大气压力计；string8=9B2331；string9=数字温湿度大气压力计；string10=9B2331；string11=101.1；string12=25.9；string13=973.39；string14=988.6；string15=986.6；string16=1.1；string17=4.20；string18=4.268；string19=4.228

### sup_rf_common / Sup_RF_Attex_Check

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark1(94%)，remark2(94%)，remark3(94%)，remark4(94%)，remark5(94%)，remark7(94%)

### sup_rf_common / Sup_RF_OCECJGMultipointCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，time1(100%)，time2(100%)，string1(98%)，string10(98%)，string11(98%)，string12(98%)

  - 样本 CH2609281790596139551 (2026-09-28 21:42:46.140000): pollutanttype=OCEC；devicebrand=CECEP；devicemodel=TR20N9；devicecode=CM10214；string1=2.1035；string4=1；string5=0；string6=0；string7=0.013；string8=0.013；string9=818；string10=2；string11=0；string12=0；string13=1133；string14=1；string15=4.2；string16=4.746；string17=0.203；string18=0.198；string19=11788；string20=2；string21=4.2；string22=4.661

### sup_rf_common / Sup_RF_HCHOCollectPercent

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string2(100%)，string3(100%)，string4(100%)，string5(100%)，string42(98%)

### sup_rf_common / Sup_RF_HCHOMLinearError

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string2(100%)，string3(100%)，string4(100%)，string5(100%)，string15(98%)

### sup_rf_common / Sup_RF_HCHODetectionLimit

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string2(100%)，string3(100%)，string4(100%)，string5(100%)，time1(98%)

### sup_rf_common / Sup_RF_HCHORepeatTest

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string2(100%)，string3(100%)，string4(100%)，string5(100%)，time1(98%)

### sup_rf_common / Sup_RF_Month_HONOCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，time1(100%)，string51(99%)，string52(99%)，string53(99%)，string54(99%)，string55(99%)

  - 样本 CH2610251792937424538 (2026-10-22 00:00:00): pollutanttype=HONO；devicebrand=wisdominc；devicemodel=LOPAP-03；devicecode=G17-3021；string51=HONO；string52=LOPAP-03；string53=张均明；string54=上海祥得；string55=江门西区

### sup_rf_common / Sup_RF_Week_TrafficFlowCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，bool_31(81%)，bool_32(81%)，bool_33(81%)，bool_34(81%)，bool_35(81%)，bool_36(81%)

### sup_rf_common / Sup_RF_TSIFlowCheckRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string6(94%)，string7(93%)，string1(86%)，string2(86%)，string3(86%)，string4(86%)

### sup_rf_common / Sup_RF_Month_HONOTest

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610251792937424538 (2026-10-22 00:00:00): pollutanttype=HONO；devicebrand=wisdominc；devicemodel=LOPAP-03；devicecode=G17-3021；string1=00；string2=0；string3=0；string4=合格；string51=HONO；string52=LOPAP-03；string53=张均明；string54=上海祥得；string55=江门西区

### sup_rf_common / Sup_RF_PTR_MSQuality

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，bool_31(82%)，bool_32(82%)，bool_33(82%)，bool_34(82%)，bool_35(82%)，bool_36(82%)

  - 样本 CH2610251792937687343 (2026-10-23 00:00:00): pollutanttype=PTR-MS；devicebrand=Pengyuchangya；devicemodel=PTR-TOF 1000；devicecode=T1-127

### sup_rf_common / Sup_RF_OCECJGSingleCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string10(100%)，string11(100%)，string14(100%)，string15(100%)，string16(100%)

### sup_rf_common / Sup_RF_Month_YT_FlowCalibration

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，time1(100%)，time2(100%)，time3(100%)，string2(99%)，string3(99%)

  - 样本 CH2610181792338054733 (2026-10-17 00:00:00): pollutanttype=NMHC；devicebrand=优泰；devicemodel=NCMS6300；devicecode=060223003；string1=陈志文；string2=KM0410-62A-1-00-0-300；string3=521016；string4=CNEMC2025-003-L1371；string5=(0-300)mL/min；string6=100.03；string7=113.62；string8=114.12；string9=-2.94；string10=100.27；string11=114.49；string12=114.99；string13=-3.45；string14=100.31；string15=114.48；string16=114.98；string17=-3.4

### sup_rf_common / Sup_RF_VoCsChromatotecCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string12(100%)，string13(100%)，string15(100%)，string17(100%)，string2(100%)，string27(100%)

### sup_rf_common / Sup_RF_Month_YT_LeakChecking

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610181792338054733 (2026-10-17 00:00:00): pollutanttype=NMHC；devicebrand=优泰；devicemodel=NCMS6300；devicecode=060223003；string1=陈志文；string4=0.0；string5=0.02；string6=合格；string7=合格

### sup_rf_common / Sup_RF_VOCsAMASamplingFlowRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string10(100%)，string11(100%)，string12(100%)，string13(100%)，string14(100%)，string15(100%)

  - 样本 CH2610211792552602903 (2026-10-21 00:00:00): pollutanttype=VOCs；devicebrand=AMA；devicemodel=GC5000；devicecode=151085300 /151086301；string1=15105301；string2=28.7；string3=15105300；string4=31；string5=ALICAT；string6=519535；string7=0.998；string8=0.085；string9=1；string10=33.3；string11=46.61；string12=25.18；string13=758.3；string14=46.6；string15=42.6；string16=1011；string17=-21.78；string18=33.3；string19=47.66；string20=25.18

### sup_rf_common / Sup_RF_OcecEnvironmentCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string11(100%)，string12(100%)，string13(100%)，string14(100%)，string15(100%)

### sup_rf_common / Sup_RF_OcecFlowVerificationCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string10(100%)，string11(100%)，string3(100%)，string4(100%)，string5(100%)，string6(100%)

  - 样本 CH2610231792740890157 (2026-10-21 00:00:00): pollutanttype=OCEC；devicebrand=FPI；devicemodel=OCEC-100；devicecode=CEF11980001；string3=ALICAT；string4=587665；string5=0.9948；string6=0.0256；string7=1；string8=20；string9=19.99；string10=19.912；string11=-0.4417；string12=否；string18=20.1；string19=21.27；string20=21.18；string21=5.37；string22=否；string28=19.6；string29=19.62；string30=19.54；string31=-0.306；string32=否

### sup_rf_common / Sup_RF_MSQualityCalibration

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string11(100%)，string12(100%)，string13(100%)，string14(100%)，string15(100%)

  - 样本 CH2609131789297697417 (2026-09-17 00:00:00): pollutanttype=SingleParticle；devicebrand=HeXin；devicemodel=SPAMS 0525；remark=Pb+参考范围为204-208；devicecode=A12501G0002S；string1=26.9；string2=45；string3=760.54；string4=SPA-MS 0525；string5=AT2501G0002S；string6=2.844Torr；string7=38.618；string8=38.906；string9=合格；string10=206.984；string11=207.118；string12=合格；string13=46.321；string14=46.855；string15=合格；string16=97.179；string17=97.4048；string18=合格

### sup_rf_common / Sup_RF_MSParticleSizeCalibration

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string12(100%)，string14(100%)，string16(100%)，string17(100%)，string2(100%)

  - 样本 CH2609131789297697417 (2026-09-17 00:00:00): pollutanttype=SingleParticle；devicebrand=HeXin；devicemodel=SPAMS 0525；remark=大气压无法填写，大气压为760.54mmHg；devicecode=A12501G0002S；string1=26.9；string2=45；string3=%RH；string4=SPA-MS 0525；string5=AT2501G0002S；string6=2.794Torr；string7=0.3；string8=501；string9=合格；string10=0.5；string11=593；string12=0.74；string13=660；string14=0.97；string15=707；string16=46.2602；string17=-1.29162；string18=1.3；string19=762

### sup_rf_common / Sup_RF_PANsRepeatabilityCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(97%)，string2(97%)，string3(97%)，string4(97%)，string10(95%)，string11(95%)

  - 样本 CH2610141791944020314 (2026-10-14 18:59:46.367000): pollutanttype=PANs；devicebrand=DADI ENCON；devicemodel=AKPAN-9000；devicecode=D1631990001；string1=AKPAN-9000；string2=D1631990001；string3=AKPAN-600；string4=CED11970008；string5=4；string6=4.022；string7=3.998；string8=3.992；string9=4.012；string10=4.053；string11=4.031；string12=4.045；string13=4.0220；string14=0.0202；string15=0.50%

### sup_rf_common / Sup_RF_VOCsEXPECSamplingFlowRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string10(100%)，string11(100%)，string12(100%)，string13(100%)，string14(100%)，string15(100%)

### sup_rf_common / Sup_RF_Week_THLiDAR

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610181792308956872 (2026-10-22 00:00:00): pollutanttype=WSKXLD；devicebrand=中科环光；devicemodel=CASEO-RM-LIDAR；devicecode=///

### sup_rf_common / Sup_RF_Week_BJCCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610181792308956872 (2026-10-22 00:00:00): pollutanttype=BJC；devicebrand=RLHG；devicemodel=RL-2D-200；devicecode=BLIP-20210203-02

### sup_rf_common / Sup_RF_PANsStabilityCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(97%)，string2(97%)，string3(97%)，string4(97%)，time1(97%)，time2(97%)

### sup_rf_common / Sup_RF_OcecHeliumMethaneCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(97%)，string10(97%)，string11(97%)，string12(97%)，string13(97%)，string14(97%)

  - 样本 CH2610211792561428196 (2026-10-21 00:00:00): pollutanttype=OCEC；devicebrand=Sunset；devicemodel=Model 4L；remark=氦气通道流量误差0.35%
氦气通道（吹扫）流量误差-0.62%
氦；devicecode=SC00073-4；string1=KMG4-62AW-1-00-0-100；string2=299899；string3=1.0034；string4=0.1167；string5=1；string6=Model 4L；string7=SC00073-4；string8=OC/EC；string9=氦甲烷通道；string10=15.0；string11=15.1；string12=15.23；string13=15.40；string14=1.99；string15=合格

### sup_rf_common / RF_W_GreenHouseCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610201792468477068 (2026-10-20 00:00:00): pollutanttype=TDL；devicebrand=HY；devicemodel=LI-7500DS；devicecode=75D-5166

### sup_rf_common / Sup_RF_VoCsTianHongCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string11(100%)，string13(100%)，string15(100%)，string17(100%)，string7(100%)，string8(100%)

### sup_rf_common / Sup_RF_Quarter_YT_NMHCRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610241792832457776 (2026-10-24 00:00:00): pollutanttype=NMHC；devicebrand=优泰；devicemodel=NCMS6300；devicecode=060223003；string1=Ntrace.2207；string2=KM0410-62A-1-00-0-300；string3=NGZ5000；string4=CNEMC2025-003-L1371；string5=空气中甲烷，丙烷气体标准物质；string6=178PPM；string7=甲烷，丙烷；string8=13PPM；string9=28；string10=38；string11=101.1；string12=陈志文；string13=0；string14=1006.62；string15=2008.85；string16=3006.22；string17=3992.61；string18=4996.96；string19=0.9999913；string20=-0.3%

### sup_rf_common / Sup_RF_OcecOrganicCarbonCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string2(100%)，string3(100%)，string4(100%)，string5(100%)，string6(100%)

### sup_rf_common / Sup_RF_TurbidiMeterRoutineCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)

### sup_rf_common / Sup_RF_TurbidiMeterCalibration

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(96%)，string10(96%)，string11(96%)，string13(96%)，string14(96%)，string15(96%)

### sup_rf_common / Sup_RF_OCECSamplingFlowCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string10(100%)，string11(100%)，string2(100%)，string3(100%)，string4(100%)

### sup_rf_common / Sup_RF_HP_Precision

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(80%)，string2(80%)，time1(80%)，time2(80%)，time3(80%)，string3(75%)

  - 样本 CH2610081791468291938 (None): pollutanttype=CO2/CH4/CO/N2O；devicebrand=世纪朝阳；devicemodel=CS2401；devicecode=5208-CFKADS2620；string1=瑞信气体；string2=200262002045；string3=427.38/2.398/0.858；string4=0.40/0/0.01；string5=0.0010/0.000/0.0150

### sup_rf_common / Sup_RF_HONOConsumablesReplace

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610161792140961445 (2026-10-21 00:00:00): pollutanttype=HONO；devicebrand=Etraninc；devicemodel=TiH203；devicecode=21820301011；string1=HONO监测仪；string2=TiH203；string3=李秉治；string4=202805壹点；string5=广州大学城站；string6=针式过滤器；string7=定期更换；string8=充足；string9=吸收液R1；string10=定期更换；string11=充足；string12=反应液R2；string13=定期更换；string14=充足；string15=蠕动泵管；string16=定期更换；string17=充足

### sup_rf_common / Sup_RF_HP_Comparability

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，time1(94%)，time2(94%)，string1(88%)，string10(88%)，string11(88%)，string12(88%)

  - 样本 CH2610081791468291938 (2026-10-09 00:00:43.637000): pollutanttype=CO2/CH4/CO/N2O；devicebrand=世纪朝阳；devicemodel=CS2401；devicecode=5208-CFKADS2620；string1=0.2920；string2=-4.1165；string3=1.000；string4=200262002089；string5=200262002048；string6=0.2970；string7=1.590；string8=0.2993；string9=1.5899；string10=200262002045；string11=0.858；string12=0.8601；string13=-3.2512；string14=-3.5432

### sup_rf_common / Sup_RF_Week_FKXLiDAR

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610181792308956872 (2026-10-22 00:00:00): pollutanttype=FKXLD；devicebrand=青岛镭测；devicemodel=WindMast PBL；devicecode=/////；string1=43.1；string2=27.9

### sup_rf_common / Sup_RF_HP_Accuracy

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(88%)，string14(88%)，string19(88%)，string2(88%)，string20(88%)，string21(88%)

  - 样本 CH2610081791468291938 (None): pollutanttype=CO2/CH4/CO/N2O；devicebrand=世纪朝阳；devicemodel=CS2401；devicecode=5208-CFKADS2620；string1=200251501042；string2=200262002089；string3=200251501045；string4=200262002045；string5=200223103166；string6=200262002048；string7=0.2385；string8=0.2970；string9=0.7863；string10=0.8580；string11=1.4800；string12=1.5900；string13=0.2384；string14=0.2993；string15=0.7772；string16=0.8594；string17=1.4656；string18=1.5899；string19=1.0057；string20=0.00

### sup_rf_common / Sup_RF_MSFlowCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string11(100%)，string12(100%)，string13(100%)，string14(100%)，string16(100%)

### sup_rf_common / Sup_RF_thybWeekCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610261792981500766 (2026-10-26 00:00:00): pollutanttype=VOCs；devicebrand=EXPEC；devicemodel=EXPEC-2000；devicecode=8B3P2550002；string1=24；string2=45%；string3=4.2；string4=2.6

### sup_rf_common / Sup_RF_VOCsChromatotecSamplingFlowRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string10(100%)，string11(100%)，string12(100%)，string13(100%)，string14(100%)

### sup_rf_common / Sup_RF_PaperTapeRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string2(100%)，string3(100%)，string4(100%)，string5(100%)，time2(100%)

### sup_rf_common / Sup_RF_VOCsWHTHSamplingFlowRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string10(100%)，string11(100%)，string12(100%)，string13(100%)，string14(100%)

### sup_rf_common / Sup_RF_DiaphragmCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string10(100%)，string11(100%)，string12(100%)，string13(100%)，string16(100%)

### sup_rf_common / Sup_RF_HalfYear_HONOCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

### sup_rf_common / Sup_RF_OCECWeekCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2610211792586421415 (2026-10-21 00:00:00): pollutanttype=OCEC；devicebrand=Bmet；devicemodel=AE33；devicecode=TCA08-S02-00293；string1=AE33；string2=TCA08-S02-00293；string3=√；string8=E；string13=17.20；string18=16.99；string23=0.60；string28=35；string33=16.7；string38=101.130；string43=33.80

### sup_rf_common / Sup_RF_HP_Calibration

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)

### sup_rf_common / Sup_RF_VoCsWHTHDetectionLimitRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(75%)

### sup_rf_common / Sup_RF_VOCsWHTHMulityPointCurveRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(38%)

### sup_rf_common / Sup_RF_Year_YT_AccuracyRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2609161789565090754 (2026-09-16 00:00:00): pollutanttype=NMHC；devicebrand=优泰；devicemodel=NCMS6300；devicecode=060223010；string1=2207；string2=090123101；string3=NGZ5000；string4=140123101；string5=156240925153；string6=122.4；string7=156240925153；string8=9.82；string9=27.1；string10=41.2；string11=101.33；string12=杨越东；string13=1023.7；string14=990.45；string15=996.96；string16=981.19；string17=1002.54；string18=961.91；string19=995.56；string20=6.13

### sup_rf_common / Sup_RF_VoCsChromatotecDetectionLimitRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(67%)

### sup_rf_common / Sup_RF_VOCsEXPECMulityPointCurveRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(33%)

### sup_rf_common / Sup_RF_VOCsSinglePointCheckQC

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(17%)

### sup_rf_common / Sup_RF_VoCsEXPECDetectionLimitRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(25%)

### sup_rf_common / Sup_RF_Year_HONOCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

### sup_rf_common / Sup_RF_Quarter_HONOCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark6(100%)，string51(100%)，string52(100%)，string53(100%)，string54(100%)，string55(100%)

### sup_rf_common / Sup_RF_TurbidiMeterSamplingCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string10(100%)，string11(100%)，string2(100%)，string9(100%)，time1(100%)

### sup_rf_common / Sup_RF_VocsStandardCurveCalibrate

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(75%)，time1(75%)，time2(75%)

### sup_rf_common / Sup_RF_QualityCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string2(100%)，string3(100%)，string4(100%)，time1(100%)，time2(100%)

### sup_rf_common / Sup_RF_Month_THLiDAR

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2609211789949635001 (2026-09-24 00:00:00): pollutanttype=WSKXLD；devicebrand=中科环光；devicemodel=CASEO-RM-LIDAR；devicecode=///

### sup_rf_common / Sup_RF_VOCsMulityPointCurveRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(100%)

### sup_rf_common / Sup_RF_VoCsDetectionLimitRecord

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(100%)

### sup_rf_common / Sup_RF_WholeDiaphargmCalibration

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，remark(100%)，string1(100%)，string10(100%)，string100(100%)，string101(100%)，string102(100%)

### sup_rf_common / Sup_RF_O3LidarRepair

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

  - 样本 CH2608061785981823352 (None): pollutanttype=O3Lidar；devicebrand=Bluedon；devicemodel=LGO-01；devicecode=LKO-012020032009；string1=LKO-012020032009；string2=2026年7月18日-7月24日；string3=激光器无法正常出光；string4=返厂检修，电路控制板异常导致；string5=维修电路控制板；string6=完成维修后安装，重新调光，光路校准，能量检查，正常运行

### sup_rf_common / Sup_RF_OCECSunsetFlowCalibration

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string1(100%)，string10(100%)，string100(100%)，string101(100%)，string102(100%)，string103(100%)

### sup_rf_common / Sup_RF_MTHNMHCAnalyzer

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_4(100%)，bool_5(100%)，bool_50(100%)，bool_6(100%)，bool_7(100%)，bool_8(100%)，bool_9(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，string11(100%)，string12(100%)，string13(100%)，string2(100%)，string4(100%)，string5(100%)

### sup_rf_common / RF_HY_GreenHouseCheck

填充列：bool_1(100%)，bool_10(100%)，bool_11(100%)，bool_12(100%)，bool_13(100%)，bool_14(100%)，bool_15(100%)，bool_16(100%)，bool_17(100%)，bool_18(100%)，bool_19(100%)，bool_2(100%)，bool_20(100%)，bool_21(100%)，bool_22(100%)，bool_23(100%)，bool_24(100%)，bool_25(100%)，bool_26(100%)，bool_27(100%)，bool_28(100%)，bool_29(100%)，bool_3(100%)，bool_30(100%)，bool_31(100%)，bool_32(100%)，bool_33(100%)，bool_34(100%)，bool_35(100%)，bool_36(100%)，bool_37(100%)，bool_38(100%)，bool_39(100%)，bool_4(100%)，bool_40(100%)，bool_41(100%)，bool_42(100%)，bool_43(100%)，bool_44(100%)，bool_45(100%)

## sup_rf_deviceflowcheck（总行数 1477，tag 数 2）

| ruleitemtag | 总行数 | 近90天 | 检查日期范围 | 监测项目 |
| --- | ---: | ---: | --- | --- |
| Sup_RF_DeviceFlowCheck | 1473 | 544 | 2025-02-11 ~ 2026-10-27 | PM1×855、NH3×110、BC×91、WaterSolubleIons×90、HeavyMetal×87 |
| Sup_RF_DeviceFlowCheck_PTRMS | 4 | 1 | 2026-02-04 ~ 2026-09-24 | PTR-MS×4 |

### sup_rf_deviceflowcheck / Sup_RF_DeviceFlowCheck

填充列：calibratedatenext1(100%)，calibratedateprev1(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，iscalibrate1(100%)，iscalibrate2(100%)，isok1(100%)，isok2(100%)，flowermodel1(98%)，flowercode1(98%)，intercept1(97%)，slope1(97%)，r1(97%)，displayvalue1(96%)，correctionvalue1(95%)，devicevalue1(94%)，targetvalue1(94%)，error1(93%)，iscalibrate3(90%)，indicationerror1(77%)，iscalibrate4(42%)，isliquidflowqualified(27%)，remark(17%)

  - 样本 CH2610271793091265127 (2026-10-27 00:00:00): pollutanttype=PM1；devicebrand=TE；devicemodel=5014i；devicecode=CM23438005；flowermodel1=Defender-520H；flowercode1=160402；calibratedateprev1=2026-02-03 00:00:00；calibratedatenext1=2027-02-02 00:00:00；slope1=1.00986；intercept1=-0.01640；r1=0.99999；targetvalue1=16.67；displayvalue1=16.546；correctionvalue1=16.69；error1=0.12；isok1=0；iscalibrate1=0；isok2=0；iscalibrate2=0；devicevalue1=16.67；indicationerror1=-0.12；iscalibrate3=0；iscalibrate4=0

### sup_rf_deviceflowcheck / Sup_RF_DeviceFlowCheck_PTRMS

填充列：calibratedatenext1(100%)，calibratedateprev1(100%)，correctionvalue1(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，devicevalue1(100%)，displayvalue1(100%)，error1(100%)，flowercode1(100%)，flowermodel1(100%)，indicationerror1(100%)，intercept1(100%)，iscalibrate1(100%)，iscalibrate2(100%)，iscalibrate3(100%)，isok1(100%)，isok2(100%)，r1(100%)，slope1(100%)，targetvalue1(100%)，iscalibrate4(50%)，correctionvalue2(25%)，devicevalue2(25%)，displayvalue2(25%)，error2(25%)，indicationerror2(25%)，isliquidflowqualified(25%)，remark(25%)，targetvalue2(25%)

  - 样本 CH2609271790522191511 (2026-09-24 00:00:00): pollutanttype=PTR-MS；devicebrand=Pengyuchangya；devicemodel=PTR-TOF 1000；devicecode=T1-127；flowermodel1=P300A-2-20SLPM；flowercode1=P1XCF1218VAAW63；calibratedateprev1=2026-01-07 00:00:00；calibratedatenext1=2027-01-06 00:00:00；slope1=1.006；intercept1=-0.0661；r1=1.0000；targetvalue1=100；displayvalue1=99.710；correctionvalue1=100.24；error1=0.24；isok1=0；iscalibrate1=0；isok2=0；iscalibrate2=0；devicevalue1=100；indicationerror1=-0.24；iscalibrate3=0；iscalibrate4=0

## sup_rf_monitorinspection（总行数 1574，tag 数 3）

| ruleitemtag | 总行数 | 近90天 | 检查日期范围 | 监测项目 |
| --- | ---: | ---: | --- | --- |
| Sup_RF_MonitorInspection_Week | 1182 | 355 | 2025-12-23 ~ 2026-10-27 | BC×1182 |
| Sup_RF_MonitorInspection_Month | 305 | 90 | 2025-12-25 ~ 2026-10-27 | BC×305 |
| Sup_RF_MonitorInspection_Quarter | 87 | 28 | 2026-01-07 ~ 2026-10-26 | BC×87 |

### sup_rf_monitorinspection / Sup_RF_MonitorInspection_Week

填充列：devicebrand(100%)，devicecode(100%)，devicemodel(100%)，formtype(100%)，monthcap(100%)，monthcutter(100%)，monthdate(100%)，monthsamplelinetube(100%)，ondemandfilter(100%)，ondemandlubrication(100%)，ondemandopticalcavity(100%)，ondemandpapertape(100%)，quarterleaktest(100%)，quartertrafficv(100%)，weekattribute(100%)，weekdatacontrol(100%)，weekdewaterbottle(100%)，weekstabilitytest(100%)，weekzeropointtest(100%)，weekdcremarks(37%)，weekaremarks(36%)，weekstremarks(33%)，weekzptremarks(32%)，weekdbremarks(32%)

  - 样本 CH2610271793071776740 (2026-10-27 00:00:00): pollutanttype=BC；devicebrand=Yiyi；devicemodel=BC1050；devicecode=C17324；formtype=Week；weekdatacontrol=0；weekattribute=0；weekdewaterbottle=0；weekzeropointtest=0；weekstabilitytest=0；monthsamplelinetube=0；monthcap=0；monthcutter=0；monthdate=0；quartertrafficv=0；quarterleaktest=0；ondemandopticalcavity=0；ondemandlubrication=0；ondemandpapertape=0；ondemandfilter=0

### sup_rf_monitorinspection / Sup_RF_MonitorInspection_Month

填充列：devicebrand(100%)，devicecode(100%)，devicemodel(100%)，formtype(100%)，monthcap(100%)，monthcutter(100%)，monthdate(100%)，monthsamplelinetube(100%)，ondemandfilter(100%)，ondemandlubrication(100%)，ondemandopticalcavity(100%)，ondemandpapertape(100%)，quarterleaktest(100%)，quartertrafficv(100%)，weekattribute(100%)，weekdatacontrol(100%)，weekdewaterbottle(100%)，weekstabilitytest(100%)，weekzeropointtest(100%)，monthcuttremarks(46%)，monthdremarks(46%)，monthsltremarks(46%)，monthcremarks(45%)，ondemandqcremarks(42%)，ondemandptremarks(41%)，ondemandfremarks(37%)，ondemandlremarks(37%)

  - 样本 CH2610271793071801475 (2026-10-27 00:00:00): pollutanttype=BC；devicebrand=Yiyi；devicemodel=BC1050；devicecode=C17324；formtype=Month；weekdatacontrol=0；weekattribute=0；weekdewaterbottle=0；weekzeropointtest=0；weekstabilitytest=0；monthsamplelinetube=0；monthcap=0；monthcutter=0；monthdate=0；quartertrafficv=0；quarterleaktest=0；ondemandopticalcavity=0；ondemandlubrication=0；ondemandpapertape=0；ondemandfilter=0

### sup_rf_monitorinspection / Sup_RF_MonitorInspection_Quarter

填充列：devicebrand(100%)，devicecode(100%)，devicemodel(100%)，formtype(100%)，monthcap(100%)，monthcutter(100%)，monthdate(100%)，monthsamplelinetube(100%)，ondemandfilter(100%)，ondemandlubrication(100%)，ondemandopticalcavity(100%)，ondemandpapertape(100%)，quarterleaktest(100%)，quartertrafficv(100%)，weekattribute(100%)，weekdatacontrol(100%)，weekdewaterbottle(100%)，weekstabilitytest(100%)，weekzeropointtest(100%)，quartertvremarks(44%)，quarterltremarks(40%)，ondemandptremarks(38%)，ondemandqcremarks(37%)，ondemandlremarks(32%)，ondemandfremarks(31%)

  - 样本 CH2610261793021486119 (2026-10-26 00:00:00): pollutanttype=BC；devicebrand=Yiyi；devicemodel=BC1050；devicecode=C12018；formtype=Quarter；weekdatacontrol=0；weekattribute=0；weekdewaterbottle=0；weekzeropointtest=0；weekstabilitytest=0；monthsamplelinetube=0；monthcap=0；monthcutter=0；monthdate=0；quartertrafficv=0；quarterleaktest=0；ondemandopticalcavity=0；ondemandlubrication=0；ondemandpapertape=0；ondemandfilter=0；quartertvremarks=正常；quarterltremarks=正常；ondemandqcremarks=正常；ondemandlremarks=正常

## sup_rf_monthnephelometercheck（总行数 4，tag 数 1）

| ruleitemtag | 总行数 | 近90天 | 检查日期范围 | 监测项目 |
| --- | ---: | ---: | --- | --- |
| Sup_RF_MonthNepheloMeterCheck | 4 | 0 | 2021-09-14 ~ 2021-10-04 | NepheloMeter×4 |

### sup_rf_monthnephelometercheck / Sup_RF_MonthNepheloMeterCheck

填充列：clsqsqj(100%)，cyfjyzqk(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，hwcytqj(100%)，yqyxcs(100%)，yqyxsz(100%)，yqzt(100%)，remark1(50%)，remark2(50%)

## sup_rf_nephelometercalibration（总行数 7，tag 数 1）

| ruleitemtag | 总行数 | 近90天 | 检查日期范围 | 监测项目 |
| --- | ---: | ---: | --- | --- |
| Sup_RF_NepheloMeterCalibration | 7 | 0 | 2021-09-14 ~ 2022-03-14 | NepheloMeter×7 |

### sup_rf_nephelometercalibration / Sup_RF_NepheloMeterCalibration

填充列：b1(100%)，b2(100%)，b3(100%)，b4(100%)，b5(100%)，b6(100%)，bz1(100%)，bz2(100%)，bz3(100%)，bz4(100%)，bz5(100%)，bz6(100%)，c1(100%)，c2(100%)，c3(100%)，c4(100%)，c5(100%)，c6(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，jzh1(57%)，jzh2(57%)，jzh3(57%)，jzh4(57%)，jzh5(57%)，jzh6(57%)

## sup_rf_pm1monitorinspection（总行数 2827，tag 数 3）

| ruleitemtag | 总行数 | 近90天 | 检查日期范围 | 监测项目 |
| --- | ---: | ---: | --- | --- |
| Sup_RF_PM1MonitorInspection_Week | 2146 | 642 | 2025-12-22 ~ 2026-10-27 | PM1×2146 |
| Sup_RF_PM1MonitorInspection_Month | 591 | 174 | 2025-12-23 ~ 2026-10-27 | PM1×591 |
| Sup_RF_PM1MonitorInspection_HalfYear | 90 | 30 | 2026-01-05 ~ 2026-10-26 | PM1×90 |

### sup_rf_pm1monitorinspection / Sup_RF_PM1MonitorInspection_Week

填充列：ahisitcalibrated(100%)，alineisitcalibrated(100%)，atisitcalibrated(100%)，btisitcomplete(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，dtisitcalibrated(100%)，externalisitclean(100%)，flowisitcalibrated(100%)，formtype(100%)，htisitcomplete(100%)，idbwhether(100%)，insideisitclean(100%)，ipisitcalibrated(100%)，isitcomplete(100%)，leakwhether(100%)，papertapeisitcalibrated(100%)，pgisitcalibrated(100%)，shwhether(100%)，spwhether(100%)，timeisitcalibrated(100%)，ttisitcomplete(100%)，otherremarks(17%)

  - 样本 CH2610271793095217863 (2026-10-27 00:00:00): pollutanttype=PM1；devicebrand=TE；devicemodel=5014i；devicecode=CM23438008；formtype=Week；dtisitcalibrated=0；ipisitcalibrated=0；flowisitcalibrated=0；alineisitcalibrated=0；timeisitcalibrated=0；papertapeisitcalibrated=0；atisitcalibrated=0；ahisitcalibrated=0；pgisitcalibrated=0；externalisitclean=0；insideisitclean=0；spwhether=0；idbwhether=0；shwhether=0；leakwhether=0；isitcomplete=0；ttisitcomplete=0；htisitcomplete=0；btisitcomplete=0

### sup_rf_pm1monitorinspection / Sup_RF_PM1MonitorInspection_Month

填充列：ahisitcalibrated(100%)，alineisitcalibrated(100%)，atisitcalibrated(100%)，btisitcomplete(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，dtisitcalibrated(100%)，externalisitclean(100%)，flowisitcalibrated(100%)，formtype(100%)，htisitcomplete(100%)，idbwhether(100%)，insideisitclean(100%)，ipisitcalibrated(100%)，isitcomplete(100%)，leakwhether(100%)，papertapeisitcalibrated(100%)，pgisitcalibrated(100%)，shwhether(100%)，spwhether(100%)，timeisitcalibrated(100%)，ttisitcomplete(100%)，currentvalue(93%)，merror(93%)，originalvalue(93%)，calibrationpoint(67%)，otherremarks(18%)

  - 样本 CH2610271793095089698 (2026-10-27 00:00:00): pollutanttype=PM1；devicebrand=TE；devicemodel=5014i；devicecode=CM23438008；formtype=Month；calibrationpoint=1235；originalvalue=7207.4；currentvalue=7275.4；merror=0.9%；dtisitcalibrated=0；ipisitcalibrated=0；flowisitcalibrated=0；alineisitcalibrated=0；timeisitcalibrated=0；papertapeisitcalibrated=0；atisitcalibrated=0；ahisitcalibrated=0；pgisitcalibrated=0；externalisitclean=0；insideisitclean=0；spwhether=0；idbwhether=0；shwhether=0；leakwhether=1

### sup_rf_pm1monitorinspection / Sup_RF_PM1MonitorInspection_HalfYear

填充列：ahisitcalibrated(100%)，alineisitcalibrated(100%)，atisitcalibrated(100%)，btisitcomplete(100%)，devicebrand(100%)，devicecode(100%)，devicemodel(100%)，dtisitcalibrated(100%)，externalisitclean(100%)，flowisitcalibrated(100%)，formtype(100%)，htisitcomplete(100%)，idbwhether(100%)，insideisitclean(100%)，ipisitcalibrated(100%)，isitcomplete(100%)，leakwhether(100%)，papertapeisitcalibrated(100%)，pgisitcalibrated(100%)，shwhether(100%)，spwhether(100%)，timeisitcalibrated(100%)，ttisitcomplete(100%)，otherremarks(18%)

  - 样本 CH2610261793022708198 (2026-10-26 00:00:00): pollutanttype=PM1；devicebrand=Bluedon；devicemodel=LGH-01E；devicecode=C211062；formtype=HalfYear；dtisitcalibrated=0；ipisitcalibrated=0；flowisitcalibrated=0；alineisitcalibrated=0；timeisitcalibrated=0；papertapeisitcalibrated=0；atisitcalibrated=0；ahisitcalibrated=0；pgisitcalibrated=0；externalisitclean=0；insideisitclean=0；spwhether=0；idbwhether=0；shwhether=0；leakwhether=1；isitcomplete=0；ttisitcomplete=0；htisitcomplete=0；btisitcomplete=0
