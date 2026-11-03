# 主网 rf_* 档案 × 广东运维平台源码 核对报告

- 生成时间：2026-11-03。方法同组分站：实体 `<summary>` 注释 + 视图标签为权威源（`rf-main-net-field-mappings.md`）。
- 核对条目：213（表,列）引用；✅实体注释 102、✅视图标签 81、🟡实体存在（无注释）13、⚠️源码未见 17。

## 汇总表

| 配置 | 表 | 上下文 | 列 | 来源 | 平台含义/标签 |
| --- | --- | --- | --- | --- | --- |
| rf_range_profiles | `RF_W_GASEOUSCHECK_CO` | check_value_fields | `DISPLAYVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_CO` | check_value_fields | `MEASUREVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_CO` | check_value_fields | `SENSORVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_NOX` | check_value_fields | `DISPLAYVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_NOX` | check_value_fields | `MEASUREVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_NOX` | check_value_fields | `SENSORVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_O3` | check_value_fields | `DISPLAYVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_O3` | check_value_fields | `MEASUREVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_O3` | check_value_fields | `SENSORVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_SO2` | check_value_fields | `DISPLAYVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_SO2` | check_value_fields | `MEASUREVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_GASEOUSCHECK_SO2` | check_value_fields | `SENSORVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_PMCHECK` | check_value_fields | `PMDISPLAYVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_PMCHECK` | check_value_fields | `PMMEASUREVALUE` | ⚠️源码未见 |  |
| rf_range_profiles | `RF_W_PMCHECK` | check_value_fields | `PMSENSORVALUE` | ⚠️源码未见 |  |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_so2_flow.unit_field（SO2 月度气态流量） | `FLOWRANGSO2` | ✅实体注释 | SO2流量范围 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_so2_flow.value_fields（SO2 月度气态流量） | `DISPLAYVALUESO2` | ✅实体注释 | SO2显示值 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_so2_flow.value_fields（SO2 月度气态流量） | `MEASUREDVALUESO2` | ✅实体注释 | SO2测量值 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_no2_flow.unit_field（NO2 月度气态流量） | `FLOWRANGNO2` | ✅实体注释 | NO2流量范围 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_no2_flow.value_fields（NO2 月度气态流量） | `DISPLAYVALUENO2` | ✅实体注释 | NO2显示值 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_no2_flow.value_fields（NO2 月度气态流量） | `MEASUREDVALUENO2` | ✅实体注释 | NO2测量值 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_co_flow.unit_field（CO 月度气态流量） | `FLOWRANGCO` | ✅实体注释 | CO流量范围 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_co_flow.value_fields（CO 月度气态流量） | `DISPLAYVALUECO` | ✅实体注释 | CO显示值 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_co_flow.value_fields（CO 月度气态流量） | `MEASUREDVALUECO` | ✅实体注释 | CO测量值 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_o3_flow.unit_field（O3 月度气态流量） | `FLOWRANGO3` | ✅实体注释 | O3流量范围 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_o3_flow.value_fields（O3 月度气态流量） | `DISPLAYVALUEO3` | ✅实体注释 | O3显示值 |
| rf_unit_profiles | `RF_M_GASEOUSFLOWCHECK` | monthly_o3_flow.value_fields（O3 月度气态流量） | `MEASUREDVALUEO3` | ✅实体注释 | O3测量值 |
| rf_unit_profiles | `RF_TW_PmFlowCheck` | tw_pm_main_flow.value_fields（两周颗粒物主流量） | `MainFlowTarget` | ✅视图标签 | 主流量设定值（l/min）_（设定温度/流量显示屏） |
| rf_unit_profiles | `RF_TW_PmFlowCheck` | tw_pm_main_flow.value_fields（两周颗粒物主流量） | `MainFlowRefer` | ✅视图标签 | 参考流量计指示的主流量值（l/min） |
| rf_unit_profiles | `RF_TW_PmFlowCheck` | tw_pm_main_flow.value_fields（两周颗粒物主流量） | `MainFlowReal` | ✅视图标签 | 主流量真实值（l/min） |
| rf_unit_profiles | `RF_TW_PmFlowCheck` | tw_pm_main_flow.value_fields（两周颗粒物主流量） | `MainFlowFixed` | ✅视图标签 | 主流量修正值（l/min） |
| rf_unit_profiles | `RF_TW_PmFlowCheck` | tw_pm_refer_flow.value_fields（两周颗粒物参比流量） | `ReferFlowTarget` | ✅视图标签 | 辅流量设定值（l/min）_（设定温度/流量显示屏） |
| rf_unit_profiles | `RF_TW_PmFlowCheck` | tw_pm_refer_flow.value_fields（两周颗粒物参比流量） | `ReferFlowRefer` | ✅视图标签 | 参考流量计指示的辅流量值（l/min） |
| rf_unit_profiles | `RF_TW_PmFlowCheck` | tw_pm_refer_flow.value_fields（两周颗粒物参比流量） | `ReferFlowReal` | ✅视图标签 | 辅流量真实值（l/min） |
| rf_unit_profiles | `RF_TW_PmFlowCheck` | tw_pm_refer_flow.value_fields（两周颗粒物参比流量） | `ReferFlowFixed` | ✅视图标签 | 辅流量修正值（l/min） |
| rf_unit_profiles | `RF_TW_PmFlowCalibrate` | tw_pm_calibrate_before_after.value_fields（颗粒物流量校准前后流量） | `Prev_A` | ✅视图标签 | 校准前 / 是 否 |
| rf_unit_profiles | `RF_TW_PmFlowCalibrate` | tw_pm_calibrate_before_after.value_fields（颗粒物流量校准前后流量） | `Prev_B` | ✅视图标签 | 校准前 / 是 否 |
| rf_unit_profiles | `RF_TW_PmFlowCalibrate` | tw_pm_calibrate_before_after.value_fields（颗粒物流量校准前后流量） | `Next_A` | ✅视图标签 | 校准后 |
| rf_unit_profiles | `RF_TW_PmFlowCalibrate` | tw_pm_calibrate_before_after.value_fields（颗粒物流量校准前后流量） | `Next_B` | ✅视图标签 | 校准后 |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_high_flow.value_fields（季度气态流量高量程点） | `RF_Valuve_85` | ✅视图标签 | 零气 / 85% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_high_flow.value_fields（季度气态流量高量程点） | `RF_Valuve_60` | ✅视图标签 | 60% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_high_flow.value_fields（季度气态流量高量程点） | `RF_Valuve_35` | ✅视图标签 | 35% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_high_flow.value_fields（季度气态流量高量程点） | `RF_Qa_85` | ✅视图标签 | 零气 / 85% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_high_flow.value_fields（季度气态流量高量程点） | `RF_Qa_60` | ✅视图标签 | 60% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_high_flow.value_fields（季度气态流量高量程点） | `RF_Qa_35` | ✅视图标签 | 35% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_high_flow.value_fields（季度气态流量高量程点） | `RF_Qs_85` | ✅视图标签 | 零气 / 85% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_high_flow.value_fields（季度气态流量高量程点） | `RF_Qs_60` | ✅视图标签 | 60% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_high_flow.value_fields（季度气态流量高量程点） | `RF_Qs_35` | ✅视图标签 | 35% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_low_flow.value_fields（季度气态流量低量程点） | `RF_Valuve_80` | ✅视图标签 | 标准气 / 80% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_low_flow.value_fields（季度气态流量低量程点） | `RF_Valuve_50` | ✅视图标签 | 50% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_low_flow.value_fields（季度气态流量低量程点） | `RF_Valuve_20` | ✅视图标签 | 20% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_low_flow.value_fields（季度气态流量低量程点） | `RF_Qa_80` | ✅视图标签 | 标准气 / 80% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_low_flow.value_fields（季度气态流量低量程点） | `RF_Qa_50` | ✅视图标签 | 50% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_low_flow.value_fields（季度气态流量低量程点） | `RF_Qa_20` | ✅视图标签 | 20% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_low_flow.value_fields（季度气态流量低量程点） | `RF_Qs_80` | ✅视图标签 | 标准气 / 80% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_low_flow.value_fields（季度气态流量低量程点） | `RF_Qs_50` | ✅视图标签 | 50% |
| rf_unit_profiles | `RF_Q_GaseousFlowCheck` | quarter_gaseous_low_flow.value_fields（季度气态流量低量程点） | `RF_Qs_20` | ✅视图标签 | 20% |
| rf_position_profiles | `RF_M_GASEOUSFLOWCHECK` | range_text_fields | `DISPLAYVALUESO2` | ✅实体注释 | SO2显示值 |
| rf_position_profiles | `RF_M_GASEOUSFLOWCHECK` | range_text_fields | `MEASUREDVALUESO2` | ✅实体注释 | SO2测量值 |
| rf_position_profiles | `RF_M_GASEOUSFLOWCHECK` | range_text_fields | `DISPLAYVALUENO2` | ✅实体注释 | NO2显示值 |
| rf_position_profiles | `RF_M_GASEOUSFLOWCHECK` | range_text_fields | `MEASUREDVALUENO2` | ✅实体注释 | NO2测量值 |
| rf_position_profiles | `RF_M_GASEOUSFLOWCHECK` | range_text_fields | `DISPLAYVALUECO` | ✅实体注释 | CO显示值 |
| rf_position_profiles | `RF_M_GASEOUSFLOWCHECK` | range_text_fields | `MEASUREDVALUECO` | ✅实体注释 | CO测量值 |
| rf_position_profiles | `RF_M_GASEOUSFLOWCHECK` | range_text_fields | `DISPLAYVALUEO3` | ✅实体注释 | O3显示值 |
| rf_position_profiles | `RF_M_GASEOUSFLOWCHECK` | range_text_fields | `MEASUREDVALUEO3` | ✅实体注释 | O3测量值 |
| rf_position_profiles | `RF_TW_PmFlowCheck` | range_text_fields | `MainFlowTarget` | ✅视图标签 | 主流量设定值（l/min）_（设定温度/流量显示屏） |
| rf_position_profiles | `RF_TW_PmFlowCheck` | range_text_fields | `MainFlowRefer` | ✅视图标签 | 参考流量计指示的主流量值（l/min） |
| rf_position_profiles | `RF_TW_PmFlowCheck` | range_text_fields | `MainFlowReal` | ✅视图标签 | 主流量真实值（l/min） |
| rf_position_profiles | `RF_TW_PmFlowCheck` | range_text_fields | `MainFlowFixed` | ✅视图标签 | 主流量修正值（l/min） |
| rf_position_profiles | `RF_TW_PmFlowCheck` | range_text_fields | `ReferFlowTarget` | ✅视图标签 | 辅流量设定值（l/min）_（设定温度/流量显示屏） |
| rf_position_profiles | `RF_TW_PmFlowCheck` | range_text_fields | `ReferFlowRefer` | ✅视图标签 | 参考流量计指示的辅流量值（l/min） |
| rf_position_profiles | `RF_TW_PmFlowCheck` | range_text_fields | `ReferFlowReal` | ✅视图标签 | 辅流量真实值（l/min） |
| rf_position_profiles | `RF_TW_PmFlowCheck` | range_text_fields | `ReferFlowFixed` | ✅视图标签 | 辅流量修正值（l/min） |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `DF_Valuve_85` | ✅视图标签 | 零气 / 85% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `DF_Valuve_60` | ✅视图标签 | 60% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `DF_Valuve_35` | ✅视图标签 | 35% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `DF_Valuve_80` | ✅视图标签 | 标准气 / 80% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `DF_Valuve_50` | ✅视图标签 | 50% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `DF_Valuve_20` | ✅视图标签 | 20% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `RF_Valuve_85` | ✅视图标签 | 零气 / 85% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `RF_Valuve_60` | ✅视图标签 | 60% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `RF_Valuve_35` | ✅视图标签 | 35% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `RF_Valuve_80` | ✅视图标签 | 标准气 / 80% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `RF_Valuve_50` | ✅视图标签 | 50% |
| rf_position_profiles | `RF_Q_GaseousFlowCheck` | range_text_fields | `RF_Valuve_20` | ✅视图标签 | 20% |
| rf_position_profiles | `RF_TW_PmFlowCalibrate` | range_text_fields | `Prev_A` | ✅视图标签 | 校准前 / 是 否 |
| rf_position_profiles | `RF_TW_PmFlowCalibrate` | range_text_fields | `Prev_B` | ✅视图标签 | 校准前 / 是 否 |
| rf_position_profiles | `RF_TW_PmFlowCalibrate` | range_text_fields | `Prev_C` | ✅视图标签 | 校准前 / 是 否 |
| rf_position_profiles | `RF_TW_PmFlowCalibrate` | range_text_fields | `Next_A` | ✅视图标签 | 校准后 |
| rf_position_profiles | `RF_TW_PmFlowCalibrate` | range_text_fields | `Next_B` | ✅视图标签 | 校准后 |
| rf_position_profiles | `RF_TW_PmFlowCalibrate` | range_text_fields | `Next_C` | ✅视图标签 | 校准后 |
| rf_position_profiles | `RF_TW_PmFlowCalibrate` | range_text_fields | `F_A` | 🟡实体存在（无注释） |  |
| rf_position_profiles | `RF_TW_PmFlowCalibrate` | range_text_fields | `F_B` | 🟡实体存在（无注释） |  |
| rf_position_profiles | `RF_TW_PmFlowCalibrate` | range_text_fields | `F_R` | 🟡实体存在（无注释） |  |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `CYYLCHECKVALUE` | ✅实体注释 | 采样压力检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `CYLLCHECKVALUE` | ✅实体注释 | 室采样流量检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `PMTCHECKVALUE` | ✅实体注释 | 参考PMT信号检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `ZWDCHECKVALUE` | ✅实体注释 | 紫外灯光强检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `YLCHECKVALUE` | ✅实体注释 | 斜率检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `JGCHECKVALUE` | ✅实体注释 | 截距检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `GYCHECKVALUE` | ✅实体注释 | 高压电源检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `FYCHECKVALUE` | ✅实体注释 | 反应室温度检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `ZYCHECKVALUE` | ✅实体注释 | 增益检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `BJCHECKVALUE` | ✅实体注释 | 背景检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `JXWDCKVALUE` | ✅实体注释 | 机箱温度 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `PZDYCKVALUE` | ✅实体注释 | 偏置电压 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `AGCCKVALUE` | ✅实体注释 | AGC |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `HWGYDLCKVALUE` | ✅实体注释 | 红外光源电流 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `CSCOCKXHCKVALUE` | ✅实体注释 | 初始CO参考信号 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `QYCKVALUE` | ✅实体注释 | 气压 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `JCQDLCKVALUE` | ✅实体注释 | 检测器电流 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `CBCHECKVALUE` | ✅视图标签 | 测量信号 (参比信号) / 1.17～1.22(API) 1.1～1.3(聚光) 20～90 mV(零气信号M)(大西比) 120～300 mV(标气信号M)(大西比) 2000～4900 mV（新先河） |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `GSWDCHECKVALUE` | ✅实体注释 | 光室温度检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_CO` | range_text_fields | `GFCCHECKVALUE` | ✅实体注释 | 相关轮温度检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `CYYLCHECKVALUE` | ✅实体注释 | 采样压力检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `CYLLCHECKVALUE` | ✅实体注释 | 室采样流量检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `CYLLIANGCHECKVALUE` | ✅实体注释 | 臭氧流量 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `PMTCHECKVALUE` | ✅实体注释 | 参考PMT信号检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `ZWDCHECKVALUE` | ✅实体注释 | 紫外灯光强检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `YLCHECKVALUE` | ✅实体注释 | 斜率检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `JGCHECKVALUE` | ✅实体注释 | 截距检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `GYCHECKVALUE` | ✅实体注释 | 高压电源检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `FYCHECKVALUE` | ✅实体注释 | 反应室温度检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `ZHLCHECKVALUE` | ✅实体注释 | 转化炉温度 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `FYSHICHECKVALUE` | ✅实体注释 | 反应室压力 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `NOXYLCHECKVALUE` | ✅实体注释 | nox斜率检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `NOXJGCHECKVALUE` | ✅实体注释 | nox截距检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `NOYLCHECKVALUE` | ✅实体注释 | no斜率检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `NOJGCHECKVALUE` | ✅实体注释 | no截距检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `ZYCHECKVALUE` | ✅实体注释 | 增益检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_NOX` | range_text_fields | `BJCHECKVALUE` | ✅实体注释 | 背景检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `CYYLCHECKVALUE` | ✅实体注释 | 采样压力检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `CYLLCHECKVALUE` | ✅视图标签 | 采样流量(试样流量/样气流量) / 800±10% ml/min(API) 0.25～0.55 LPM(EC) 720～880 SCCM(聚光) 0.400～1.400 L/min(赛默飞A，B路) 300～1200 ml/min(天虹) 1.2～1.7 L/min(大西比) 800±80 ml/min(新先河) |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `CYLLBCHECKVALUE` | ✅视图标签 | 采样流量(试样流量/样气流量) / 800±10% ml/min(API) 0.25～0.55 LPM(EC) 720～880 SCCM(聚光) 0.400～1.400 L/min(赛默飞A，B路) 300～1200 ml/min(天虹) 1.2～1.7 L/min(大西比) 800±80 ml/min(新先河) |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `PMTCHECKVALUE` | ✅实体注释 | 参比信号检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `ZWDCHECKVALUE` | ✅实体注释 | 紫外灯光强检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `ZWDBCHECKVALUE` | ✅视图标签 | 参比信号(参比电压/紫外参考检测器信号/模拟电压) / 2500～4800 mV(API) 1.5～4.096 V(聚光) 500～4800 mV(ESA) 45000～150000 HZ(赛默飞) 2300～5200 mV(天虹) 2000～4900 mV(新先河) |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `YLCHECKVALUE` | ✅实体注释 | 斜率检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `JGCHECKVALUE` | ✅实体注释 | 截距检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `GYCHECKVALUE` | ✅实体注释 | 高压电源检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `GYBCHECKVALUE` | ✅视图标签 | 测量信号(测量电压/紫外测量检测器信号) / 2500～4800 mV(API) 1.5～4.096 V(聚光) 500～4800 mV(ESA) 45000～150000 HZ(赛默飞) 2300～5200 mV(天虹) 2000～4900 mV(新先河) |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `FYCHECKVALUE` | ✅实体注释 | 反应室温度检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `GQCKVALUEA` | ✅实体注释 | 光强A |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `GQCKVALUEB` | ✅实体注释 | 光强B |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `CLXHCKVALUE` | ✅实体注释 | 测量信号 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `YPWDCKVALUE` | ✅实体注释 | 样品温度 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_O3` | range_text_fields | `DDLCKVALUE` | ✅实体注释 | 灯电流 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `CYYLCHECKVALUE` | ✅实体注释 | 采样压力检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `CYLLCHECKVALUE` | ✅实体注释 | 室采样流量检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `PMTCHECKVALUE` | ✅实体注释 | 参考PMT信号检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `ZWDCHECKVALUE` | ✅实体注释 | 紫外灯光强检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `YLCHECKVALUE` | ✅实体注释 | 斜率检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `JGCHECKVALUE` | ✅实体注释 | 截距检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `GYCHECKVALUE` | ✅实体注释 | 高压电源检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `FYCHECKVALUE` | ✅实体注释 | 反应室温度检查值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `PTMCKVALUE` | ✅实体注释 | PMT 温度 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `GYGCKVALUE` | ✅实体注释 | 干扰光 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `PTMDYCKVALUE` | ✅实体注释 | PMT电压 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `ZWDDYCKVALUE` | ✅实体注释 | 紫外灯电压 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `DBJZCKVALUE` | ✅实体注释 | 灯背景值 |
| rf_position_profiles | `RF_W_GASEOUSCHECK_SO2` | range_text_fields | `ZWDDLCKVALUE` | ✅实体注释 | 紫外灯电流 |
| rf_position_profiles | `RF_W_PMCHECK` | range_text_fields | `MAINFLOWVALUE` | ✅实体注释 | 流量检查值 |
| rf_position_profiles | `RF_W_PMCHECK` | range_text_fields | `AIRTEMPVALUE` | ✅实体注释 | 采样管温度检查值 |
| rf_calibration_date_profiles | `RF_W_GASEOUSCHECK_O3` | reference_time_fields | `CHECKDATE` | ⚠️源码未见 |  |
| rf_calibration_date_profiles | `RF_W_GASEOUSCHECK_O3` | reference_time_fields | `CALIBRATIONDATE` | ✅实体注释 | 校准日期 |
| rf_calibration_date_profiles | `RF_W_GASEOUSCHECK_O3` | reference_time_fields | `CREATEDATE` | ✅实体注释 | 创建日期 |
| rf_calibration_date_profiles | `RF_W_GASEOUSCHECK_O3` | pairs[臭氧传递标准有效期].prev_field | `CDDATE` | ✅视图标签 | 传递标准型号： / 传递时间 |
| rf_calibration_date_profiles | `RF_W_GASEOUSCHECK_O3` | pairs[臭氧传递标准有效期].next_field | `YXQDATE` | ✅视图标签 | 传递标准编号： / 有效期 |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | reference_time_fields | `SdtTime` | ✅视图标签 | 操作日期 / 开始时间 / 结束时间 |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | reference_time_fields | `CHECKDATE` | 🟡实体存在（无注释） |  |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | reference_time_fields | `CALIBRATIONDATE` | ⚠️源码未见 |  |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | reference_time_fields | `CREATEDATE` | ✅视图标签 | 操作日期 / 开始时间 / 结束时间 |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[温度计校准有效期].prev_field | `T_CalibrateDatePrev` | ✅视图标签 | 上次校准日期 / 下次校准日期 / 真实值(Ta) |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[温度计校准有效期].next_field | `T_CalibrateDateNext` | ✅视图标签 | 上次校准日期 / 下次校准日期 / 真实值(Ta) |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[压力计校准有效期].prev_field | `P_CalibrateDatePrev` | ✅视图标签 | 上次校准日期 / 截距 / 测量显示值 |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[压力计校准有效期].next_field | `P_CalibrateDateNext` | ✅视图标签 | 下次校准日期 / 截距 / 真实值(Pa) |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[流量计1校准有效期].prev_field | `F_CalibrateDatePrev1` | ✅视图标签 | 零气 |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[流量计1校准有效期].next_field | `F_CalibrateDateNext1` | ✅视图标签 | 零气 |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[流量计2校准有效期].prev_field | `F_CalibrateDatePrev2` | ✅视图标签 | 标准气 |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[流量计2校准有效期].next_field | `F_CalibrateDateNext2` | ✅视图标签 | 标准气 |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[动态校准仪校准有效期].prev_field | `D_CalibrateDatePrev` | ✅视图标签 | 流量检查日期 / 上一次 / 零气 |
| rf_calibration_date_profiles | `RF_Q_GaseousFlowCheck` | pairs[动态校准仪校准有效期].next_field | `D_CalibrateDateNext` | ✅视图标签 | 下一次 / 标准气 |
| rf_calibration_date_profiles | `RF_TW_PmFlowCheck` | reference_time_fields | `CHECKDATE` | ✅实体注释 | 检查日期 |
| rf_calibration_date_profiles | `RF_TW_PmFlowCheck` | reference_time_fields | `CheckSdt` | ✅视图标签 | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| rf_calibration_date_profiles | `RF_TW_PmFlowCheck` | reference_time_fields | `CREATEDATE` | ✅实体注释 | 创建日期 |
| rf_calibration_date_profiles | `RF_TW_PmFlowCheck` | pairs[流量计校准有效期].prev_field | `F_PrevDate` | 🟡实体存在（无注释） |  |
| rf_calibration_date_profiles | `RF_TW_PmFlowCheck` | pairs[流量计校准有效期].next_field | `F_NextDate` | 🟡实体存在（无注释） |  |
| rf_calibration_date_profiles | `RF_TW_PmFlowCheck` | pairs[颗粒物仪器校准有效期].prev_field | `PM_PrevDate` | 🟡实体存在（无注释） |  |
| rf_calibration_date_profiles | `RF_TW_PmFlowCheck` | pairs[颗粒物仪器校准有效期].next_field | `PM_NextDate` | 🟡实体存在（无注释） |  |
| rf_calibration_date_profiles | `RF_TW_PmFlowCalibrate` | reference_time_fields | `CHECKDATE` | ✅实体注释 | 检查日期 |
| rf_calibration_date_profiles | `RF_TW_PmFlowCalibrate` | reference_time_fields | `CheckSdt` | ✅视图标签 | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| rf_calibration_date_profiles | `RF_TW_PmFlowCalibrate` | reference_time_fields | `CREATEDATE` | ✅实体注释 | 创建日期 |
| rf_calibration_date_profiles | `RF_TW_PmFlowCalibrate` | pairs[流量计校准有效期].prev_field | `F_PrevDate` | 🟡实体存在（无注释） |  |
| rf_calibration_date_profiles | `RF_TW_PmFlowCalibrate` | pairs[流量计校准有效期].next_field | `F_NextDate` | 🟡实体存在（无注释） |  |
| rf_calibration_date_profiles | `RF_TW_PmFlowCalibrate` | pairs[颗粒物仪器校准有效期].prev_field | `PM_PrevDate` | 🟡实体存在（无注释） |  |
| rf_calibration_date_profiles | `RF_TW_PmFlowCalibrate` | pairs[颗粒物仪器校准有效期].next_field | `PM_NextDate` | 🟡实体存在（无注释） |  |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_CO` | reference_time_fields | `CALIBRATIONDATE` | ✅实体注释 | 校准日期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_CO` | reference_time_fields | `CREATEDATE` | ✅实体注释 | 创建日期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_CO` | pairs[标气有效期].next_field | `PPMCODEDATE` | ✅实体注释 | 标气瓶有效期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_NO2` | reference_time_fields | `CALIBRATIONDATE` | ✅实体注释 | 校准日期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_NO2` | reference_time_fields | `CREATEDATE` | ✅实体注释 | 创建日期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_NO2` | pairs[标气有效期].next_field | `PPMCODEDATE` | ✅实体注释 | 标气瓶有效期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_O3` | reference_time_fields | `CALIBRATIONDATE` | ✅实体注释 | 校准日期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_O3` | reference_time_fields | `CREATEDATE` | ✅实体注释 | 创建日期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_O3` | pairs[标气有效期].next_field | `PPMCODEDATE` | ✅实体注释 | 标气瓶有效期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_SO2` | reference_time_fields | `CALIBRATIONDATE` | ✅实体注释 | 校准日期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_SO2` | reference_time_fields | `CREATEDATE` | ✅实体注释 | 创建日期 |
| rf_calibration_date_profiles | `RF_Q_GASEOUSMULTIPOINT_SO2` | pairs[标气有效期].next_field | `PPMCODEDATE` | ✅实体注释 | 标气瓶有效期 |
| rf_enum_profiles | `RF_W_OTHERDEVICECHECK` | enum（气象仪是否正常） | `IsOk1` | ✅视图标签 | 清扫气象五参数仪或气象六参数仪（多个雨量传感器），检查设备状态，正常或故障 |
| rf_enum_profiles | `RF_W_OTHERDEVICECHECK` | enum（能见度仪是否正常） | `IsOk2` | ✅视图标签 | 清扫能见度仪，检查设备状态，正常或故障 |
| rf_enum_profiles | `RF_W_OTHERDEVICECHECK` | enum（城市摄影是否正常） | `IsOk3` | ✅视图标签 | 是否故障送修 |
| rf_enum_profiles | `RF_W_OTHERDEVICECHECK` | enum（数据采集仪是否正常） | `IsOk4` | ✅视图标签 | 是否维护雨量传感器 |
| rf_enum_profiles | `RF_TW_PmFlowCalibrate` | enum（是否校准） | `IsCalibrate` | 🟡实体存在（无注释） |  |

## 关键结论（需复核）

1. **RF_W_GASEOUSCHECK_{CO,NOX,O3,SO2} 的 DISPLAYVALUE/MEASUREVALUE/SENSORVALUE（12 条）与 RF_W_PMCHECK 的 PM_{DISPLAY,MEASURE,SENSOR}VALUE（3 条）在 GD 实体与视图中均不存在**——这 5 张表单实际字段为 LDPYPPB（零点漂移）/KDPY（跨度漂移）/MCLPPM（满程量浓度）/MAINFLOWVALUE 等，且视图标签内含品牌阈值（如 API/聚光/赛默飞/先河）。`rf_range_profiles.check_value_fields` 若继续引用不存在的列，`RF_RANGE_OUT_OF_SPEC` 对这 5 张表将空转；建议改用真实字段并接入视图标签阈值。
2. **RF_W_GASEOUSCHECK_O3.CHECKDATE**：GD 实体直接继承 CustomEntity，未映射该列（部分实体映射），数据侧可能仍有该列；风险低，建议取数时以数据侧列名为准。
3. **RF_Q_GaseousFlowCheck.CALIBRATIONDATE**：GD 实体含 CHECKDATE/CHECKDATE2 而无 CALIBRATIONDATE——疑为旧列名，建议核对数据侧（`ops_work_order_audit_aliases.py` 同表别名未含该列）。

## 未见于源码的条目（明细）

- **rf_range_profiles** / `RF_W_GASEOUSCHECK_CO` / check_value_fields / `DISPLAYVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_CO` / check_value_fields / `MEASUREVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_CO` / check_value_fields / `SENSORVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_NOX` / check_value_fields / `DISPLAYVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_NOX` / check_value_fields / `MEASUREVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_NOX` / check_value_fields / `SENSORVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_O3` / check_value_fields / `DISPLAYVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_O3` / check_value_fields / `MEASUREVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_O3` / check_value_fields / `SENSORVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_SO2` / check_value_fields / `DISPLAYVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_SO2` / check_value_fields / `MEASUREVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_GASEOUSCHECK_SO2` / check_value_fields / `SENSORVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_PMCHECK` / check_value_fields / `PMDISPLAYVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_PMCHECK` / check_value_fields / `PMMEASUREVALUE` → ⚠️源码未见
- **rf_range_profiles** / `RF_W_PMCHECK` / check_value_fields / `PMSENSORVALUE` → ⚠️源码未见
- **rf_calibration_date_profiles** / `RF_W_GASEOUSCHECK_O3` / reference_time_fields / `CHECKDATE` → ⚠️源码未见
- **rf_calibration_date_profiles** / `RF_Q_GaseousFlowCheck` / reference_time_fields / `CALIBRATIONDATE` → ⚠️源码未见
