# 组分站表单 品牌/版本 变体字典（广东运维平台源码）

- 生成时间：2026-11-03。来源：`D:\广东运维平台\trunk`（SummerFresh .NET 源码）。
- 用途：审核规则按 `ruleitemtag` 建档时，明确同一 tag 在不同**品牌**、不同**工单创建时间（版本）**下的表单差异，避免用单一布局解读历史工单。

## 一、平台选择机制

### 1. 版本选择（覆盖最广，50+ tag）

- 控制器：`var version = DataHelper.GetSysVersion("<tag>", CreateTime);`
- 配置表：`SYS_VersionConfig`（`SummerFresh.Maintenance/Entity/Sys/SYS_VersionConfig.cs`：`Type/Sdt/Edt/Version`，按**工单创建时间**落在 [Sdt, Edt) 窗口决定版本号）。
- 视图拼接：`view = "<tag>"`；`version` 非空且非 `v0` 时 `view = "<tag>_" + version`（如 `Sup_RF_DeviceFlowCheck_v2`）。
- 例：`QcFormWeekController.Sup_RF_AmbientTemperature`（L62-70）。

### 2. 品牌分支（控制器硬编码，9 处）

| tag | 品牌（`DEVICEBRAND`） | 条件 | 行为 |
| --- | --- | --- | --- |
| Sup_RF_AmbientTemperature | Etraninc（伊创） | 无条件 | 用基础视图，跳过版本选择 |
| Sup_RF_DeviceFlowCheck | Etraninc / wisdominc（唯思德） | CreateTime > 2026-08-31 | `Month/Sup_RF_DeviceFlowCheck_v3`（新增液体流量检查单位） |
| Sup_RF_DeviceFlowCheck | Etraninc | ≤ 2026-08-31 | 基础视图 |
| Sup_RF_Week_HONOCheck | Etraninc | 无条件 | `Sup_RF_Week_HONOCheck_Etraninc` 品牌视图 |
| Sup_RF_Week_HONOQC | Etraninc | 无条件 | `Sup_RF_Week_HONOQC_Etraninc` 品牌视图 |
| Sup_RF_Month_HONOCheck | Etraninc | 无条件 | `Sup_RF_Month_HONOCheck_Etraninc` 品牌视图 |
| Sup_RF_HalfYear_HONOCheck | Etraninc | 无条件 | `Sup_RF_HalfYear_HONOCheck_Etraninc` 品牌视图 |
| Sup_RF_OCECWeekCheck | Bmet（赛克码） | CreateTime ≥ 2026-09-01 | 切独立表单 `Sup_RF_Check_OCEC_Bmet`（另有 `_v1`） |
| Sup_RF_thybWeekCheck | EXPEC（谱育） | CreateTime ≥ 2026-08-13 | 切独立表单 `Sup_RF_Check_Vocs_EXPEC`（另有 `_v1`） |

品牌名证据：控制器注释——「伊创或唯思德新增液体流量检查单位」（Etraninc/wisdominc）、「赛克码OCEC新周巡检工单」（Bmet）、「谱育 VOOCs新周巡检工单」（EXPEC）。

### 3. 品牌字典表（运行时数据，非源码常量）

| 表 | 实体 | 字段 |
| --- | --- | --- |
| Sup_QCDeviceBrand | `Entity/Sup/QCDevice/Sup_QCDeviceBrand.cs` | `BrandCode`（品牌 code）、`BrandName`、`Factory`、`Batch` |
| Sup_DeviceBrand | `Services/Sup/DeviceBrandService.cs` | 同上（设备品牌） |
| BSD_DEVICEBRAND / DEVDeviceBrand | `Entity/BrandModel/BSD_DEVICEBRAND.cs`、`Entity/DEV/DEVDeviceBrand.cs` | 主网品牌字典 |

设备当前品牌取自 `Sup_Device.DEVICEBRAND`（控制器统一用法）；审核报告如需显示品牌中文名，建议 join `Sup_QCDeviceBrand.BrandName`。

## 二、版本视图清单（`_vN.cshtml`，节选）

- **多版本（v1~v3）**：`Sup_RF_DeviceFlowCheck_v1/v2/v3`、`Sup_RF_MultiCalibration_v0/v1/v3`、`Sup_RF_EquipmentMaintenance_v1/v2`、`Sup_RF_MaintenanceRecord_v1/v2`。
- **双版本**：`Sup_RF_AmbientTemperature_v1`、`Sup_RF_ChannelFlowCalibration_v2`、`Sup_RF_ChromatotecQuarterMaintain_v1`、`Sup_RF_DailyInspection_v1`、`Sup_RF_GACMonthMaintain_v1`、`Sup_RF_HP_StationCheck_v1`、`Sup_RF_NMHCAnalyzerRecord_v1`、`Sup_RF_OCECHalfYearCheck_v1`、`Sup_RF_OCECJGMultipointCheck_v1`、`Sup_RF_OCECJGWeekCheck_v1`、`Sup_RF_OCECMonthCheck_v1`、`Sup_RF_OCECMultipointCheck_v1` 等（共 25+ 个 `_vN` 视图）。
- 品牌专用视图：`Sup_RF_Week_HONOCheck_Etraninc`、`Sup_RF_Week_HONOQC_Etraninc`、`Sup_RF_Month_HONOCheck_Etraninc`、`Sup_RF_HalfYear_HONOCheck_Etraninc`、`Week/Sup_RF_Check_OCEC_Bmet(_v1)`、`Week/Sup_RF_Check_Vocs_EXPEC(_v1)`。

> 版本窗口与历史数据：`SYS_VersionConfig` 是运行时数据表，窗口起止需从库中读取；本机无库访问，故只记录机制与清单。

## 三、对审核的影响与建议

1. **同 tag 不同布局**：`sup_form_profiles.yaml` 按 tag 建档（如 `Sup_RF_DeviceFlowCheck` 的 error/indication 列），但历史工单可能来自 v1/v2/v3 或品牌专用视图——列位可能不同。当前数据普查（`column-semantics.md`）混合各版本样本，样本值一致时可直接覆盖；**对 2026 年 8~9 月后的 Bmet/EXPEC 独立表单，需单独抽样确认**（`Sup_RF_Check_OCEC_Bmet`、`Sup_RF_Check_Vocs_EXPEC`）。
2. **审核规则按 tag+期间**：建议二阶段在档案层增加可选 `valid_from/valid_to` 与 `brand_code` 字段（默认全期/全品牌），仅在出现版本差异的 tag 上使用。
3. **报告文案**：品牌名可从 `Sup_QCDeviceBrand` 映射（Etraninc=伊创、wisdominc=唯思德、Bmet=赛克码、EXPEC=谱育），避免报告里直接出现 code。
4. **版本感知抽样**：在部署环境抽查近 90 天工单的 `CreateTime` 与视图版本分布（按 tag），确认哪些 tag 实际发生过版本切换。
