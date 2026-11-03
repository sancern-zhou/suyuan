# 主网枚举档案 × 广东运维平台源码 核对报告

- 生成时间：2026-11-03。范围：`rf_enum_profiles.yaml`（枚举字段校验 + 污染物类型期望）。
- 方法：GD 实体属性类型 + 表单视图 radio/select 选项 + 相关服务赋值逻辑为权威源。

## 一、枚举字段校验（profiles）

### RF_W_OTHERDEVICECHECK.IsOk1–IsOk4（已修正 2 处标签）

GD 实体 `RF_W_OTHERDEVICECHECK.cs` L127–130 为 `bool IsOk1..IsOk4`；视图 `Views/ReportForms/RF_W_OtherDeviceCheck.cshtml` L73–95 的 radio 与标签为：

| 字段 | 源码标签（radio 选项） | 原档案标签 | 处理 |
| --- | --- | --- | --- |
| IsOk1 | 清扫气象五/六参数仪，正常/故障 | 气象仪是否正常 | 语义一致，保留 |
| IsOk2 | 清扫能见度仪，正常/故障 | 能见度仪是否正常 | 语义一致，保留 |
| IsOk3 | **是否故障送修**（是/否） | 城市摄影是否正常 ✗ | **已按源码更正** |
| IsOk4 | **是否维护雨量传感器**（是/否） | 数据采集仪是否正常 ✗ | **已按源码更正** |

补充说明：**城市摄影系统与数据采集仪是文本字段**——`CITYCAMERADEVICEMODEL/CITYCAMERASITUATION`、`DATAACQUISITIONDEVICEMODEL/DATAACQUISITIONSITUATION`（视图 L55–66），不是 IsOk3/IsOk4。原档案把这两个业务对象错配到布尔字段上。allowed_values `["0","1","0.0","1.0"]` 对 bool radio 成立，无需改动。

### RF_TW_PmFlowCalibrate.IsCalibrate（核实无误）

- 实体 `RF_TW_PmFlowCalibrate.cs`：`public bool IsCalibrate { get; set; }`。
- 视图 `Views/ReportForms/RF_TW_PmFlowCalibrate.cshtml` L139–140：radio「是/否」。
- 档案 `allowed_values: ["0","1","0.0","1.0","是","否"]` 兼容，保留。

## 二、污染物类型校验（pollutant_type_profiles）

8 张表（RF_W_GASEOUSCHECK_{CO,NOX,O3,SO2}、RF_Q_GASEOUSMULTIPOINT_{CO,NO2,O3,SO2}）的 `POLLUTANTTYPE` 由计划任务 `taskItem.POLLUTANTTYPE` 写入（`MTC/CheckOrderService.cs` L353 等），表单视图仅回填显示。

需要留意的口径差异：
- 质检回传（QUL）中，`RF_W_GASEOUSCHECK_NOX` 的污染物用的是 `QULPollutant.NO`（`QULEmun.cs` L69: `[Description("NO")] NO = 107`），而档案期望 `NOX`。
- 二者不是同一字段（QUL_QUALITYDATE.pollutantType vs 表单 POLLUTANTTYPE），**不直接构成错误**；但建议用数据侧确认 RF_W_GASEOUSCHECK_NOX 的 POLLUTANTTYPE 实际取值是 `NOX` 还是 `NO`，避免 `RF_ENUM_VALUE_INVALID` 误报。

同样建议抽查：`RF_Q_GASEOUSMULTIPOINT_NO2` 的期望值 `NO2` 与计划侧命名（NOX/NO2）是否一致。

## 三、结论

1. `rf_enum_profiles.yaml` 的 IsOk3/IsOk4 标签已按 GD 源码更正（报告文案将不再出现"城市摄影/数据采集仪是否正常"的误标）。
2. IsCalibrate 与取值集合核实无误。
3. pollutant_type_profiles 的 NOX/NO2 口径需要一次数据侧抽查（本机无法连库，建议在部署环境用 1 条近 90 天样本核对）。
