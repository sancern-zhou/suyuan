# 组分站表单 列名→字段含义 权威映射 v2（广东运维平台源码）

- **主源**：广东运维平台 `.NET` 源码 `D:\广东运维平台\trunk`——
  ① 实体类 `SummerFresh.Maintenance/Entity/Sup/**`（403 类）：属性 `<summary>` 注释即列含义（平台 ORM 列名=属性名小写）；
  ② 表单视图 `SummerFresh.MVC/Areas/Sup/Views/QcForm/**`（298 模板）：中文标签 ↔ `@Html.TextBoxFor(m => m.列)` 绑定 + `validator` 校验器（required/double 等）。
- **交叉验证**：省产品仓库 DM 分支 101 个 `Sup_*.vue`（源自这些 cshtml 的移植版）——组件头部「字段映射」注释；与 `column-semantics.md` 数据普查相互印证。
- 周期后缀 tag（`_Week/_Month/_Quarter/_HalfYear/_Year`）与实体/视图按去后缀主干匹配（同一表族共用布局，标题含周期）。
- 本文档由 `.zcode/tmp/opa-audit-rules/` 脚本生成（parse_gd_full.py → build_final_docs.py），可直接指导 `sup_form_profiles.yaml` 档案 confirmed 化。

覆盖：DB tag 共 170——实体注释 169、cshtml 标签 165、Vue 映射 47；三层全无 1 个。

## RF_D_GreenHouseCheck（sup_rf_common）
- 《组分仪器工单规则》：（温室气体相关）
- 源码依据：（三层源码均未覆盖，待业务确认）


## RF_HY_GreenHouseCheck（sup_rf_common）
- 《组分仪器工单规则》：（温室气体相关）
- 源码依据：实体 `RF_HY_GreenHouseCheck`


## RF_W_GreenHouseCheck（sup_rf_common）
- 《组分仪器工单规则》：（温室气体相关）
- 源码依据：实体 `RF_W_GreenHouseCheck`


## Sup_RF_AmbientTemperature（sup_rf_ambienttemperature）
- 源码依据：实体 `Sup_RF_AmbientTemperature`、视图 `Sup_RF_AmbientTemperature.cshtml`、Vue 移植版 x5

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `p_r` | 上次校准日期 | cshtml 标签 |
| `p_code` | 出厂编号 / 斜率 / 截距 / 相关系数 | cshtml 标签 |
| `t_code` | 设备型号 / 出厂编号 | cshtml 标签 |
| `p_model` | 设备型号 / 校准方程(Y_真实值，X_显示值) | cshtml 标签 |
| `p_slope` | 上次校准日期 | cshtml 标签 |
| `t_model` | 设备型号 / 出厂编号 | cshtml 标签 |
| `t_range` | 测量范围 / 示值修正量 | cshtml 标签 |
| `t_revised` | 测量范围 / 示值修正量 | cshtml 标签 |
| `p_nextdate` | 下次校准日期 | cshtml 标签 |
| `p_prevdate` | 上次校准日期 | cshtml 标签 |
| `t_nextdate` | 上次校准日期 / 下次校准日期 | cshtml 标签 |
| `t_prevdate` | 上次校准日期 / 下次校准日期 | cshtml 标签 |
| `p_intercept` | 上次校准日期 | cshtml 标签 |
| `p_r_revised` | 校准前 / 校准后 | cshtml 标签 |
| `t_r_revised` | 校准前 / 校准后 | cshtml 标签 |
| `p_r_standard` | 校准前 / 校准后 | cshtml 标签 |
| `t_r_standard` | 校准前 / 校准后 | cshtml 标签 |
| `p_r_nextvalue` | 校准前 / 校准后 | cshtml 标签 |
| `p_r_prevvalue` | 校准前 / 校准后 | cshtml 标签 |
| `t_r_nextvalue` | 校准前 / 校准后 | cshtml 标签 |
| `t_r_prevvalue` | 校准前 / 校准后 | cshtml 标签 |
| `p_iscalibrated` | 压力校准结果 - 是否校准 | 实体注释 |
| `t_iscalibrated` | 温度校准结果 - 是否校准 | 实体注释 |

**平台校验器：**`p_code`=required；`p_intercept`=required,double；`p_model`=required；`p_r`=required,double；`p_r_nextvalue`=required,double；`p_r_prevvalue`=required,double；`p_r_revised`=required,double；`p_r_standard`=required,double；`p_slope`=required,double；`t_code`=required；`t_model`=required；`t_r_nextvalue`=required,double；`t_r_prevvalue`=required,double；`t_r_revised`=required,double；`t_r_standard`=required,double；`t_range`=required；`t_revised`=required,double


## Sup_RF_Attex_Check（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/臭氧激光雷达.docx + 颗粒物组分/颗粒物激光雷达.docx
- 源码依据：实体 `Sup_RF_Attex_Check`、视图 `Sup_RF_Attex_Check.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `remark1` | 1 / 仪器卫生检查 / 仪器表面及散热风扇滤网积灰检查 | cshtml 标签 |
| `remark2` | 2 / 仪器参数设置检查 / 各参数设置在规定阈值范围内 | cshtml 标签 |
| `remark3` | 3 / 软件运行状态检查 / 软件无报错及卡死 | cshtml 标签 |
| `remark4` | 4 / Teflon盖子 / 卫生状态是否正常 | cshtml 标签 |
| `remark5` | 5 / 仪器运行状态检查 / 电机运转是否正常 | cshtml 标签 |
| `remark7` | 6 / 通信检查 / 检查通信模块是否正常 | cshtml 标签 |


## Sup_RF_BCYearMaintain（sup_rf_bcyearmaintain）
- 《组分仪器工单规则》：颗粒物组分/BC.docx
- 源码依据：实体 `Sup_RF_BCYearMaintain`、视图 `Sup_RF_BCYearMaintain.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bz1` | 1 / 气路清洁 | cshtml 标签 |
| `bz2` | 2 / 分析腔体清洁 | cshtml 标签 |
| `bz3` | 3 / 采样泵维护 | cshtml 标签 |
| `qgqqj` | 1 / 气路清洁 | cshtml 标签 |
| `rmark` | 备注： | cshtml 标签 |
| `wdxcs` | 3 / 采样泵维护 | cshtml 标签 |
| `qjkqcs` | 2 / 分析腔体清洁 | cshtml 标签 |


## Sup_RF_CO2DeviceMaintain（sup_rf_co2devicemaintain）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_CO2DeviceMaintain`、视图 `Sup_RF_CO2DeviceMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `datetime1` | 1 / 每月清洗一次制冷系统过滤网 | cshtml 标签 |
| `datetime2` | 2 / 每月清洁仪器风扇防尘网 | cshtml 标签 |
| `datetime3` | 3 / 仪器时钟检查；数据采集仪时钟检查 | cshtml 标签 |
| `datetime4` | 4 / 仪器显示数据和数据采集仪之间的一致性检查 | cshtml 标签 |


## Sup_RF_CO2HalfYearDeviceMaintain（sup_rf_co2halfyeardevicemaintain）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_CO2HalfYearDeviceMaintain`、视图 `Sup_RF_CO2HalfYearDeviceMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `datetime1` | 1 / 清洁内部光路 | cshtml 标签 |
| `datetime2` | 2 / 清洁内部气路 | cshtml 标签 |


## Sup_RF_CO2Inspection（sup_rf_co2inspection）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_CO2Inspection`、视图 `Sup_RF_CO2Inspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `mpa` | 标气瓶压力(MPa) | cshtml 标签 |
| `ppb` | 校准日期 / 使用满量程（PPM） | cshtml 标签 |
| `ppm` | 标气瓶编号 / 标气瓶浓度（PPM） | cshtml 标签 |
| `kdpy` | 跨度漂移(％) | cshtml 标签 |
| `mclppm` | 满量程的80％ | cshtml 标签 |
| `ldpyppb` | 零点漂移(PPM) | cshtml 标签 |
| `ppmcode` | 标气瓶编号 / 标气瓶浓度（PPM） | cshtml 标签 |
| `remark1` | 偏移电压 / -130~-100 V（赛默飞） | cshtml 标签 |
| `remark2` | AGC强度 / 150000~300000 Hz（赛默飞） | cshtml 标签 |
| `remark3` | 采样压力 / 250～1000mmHg(赛默飞) | cshtml 标签 |
| `remark4` | 采样流量 / 0.350～1.500L/min(赛默飞) | cshtml 标签 |
| `remark5` | 机内温度 / 8～47℃(赛默飞) | cshtml 标签 |
| `remark6` | 光室温度 / 47～51℃(赛默飞) | cshtml 标签 |
| `remark7` | 斜率(Slope) / 0.500～2.000(赛默飞) | cshtml 标签 |
| `remark8` | 截距(Offset) / ＞-15(赛默飞) | cshtml 标签 |
| `string1` | 偏移电压 / -130~-100 V（赛默飞） | cshtml 标签 |
| `string2` | AGC强度 / 150000~300000 Hz（赛默飞） | cshtml 标签 |
| `string3` | 采样压力 / 250～1000mmHg(赛默飞) | cshtml 标签 |
| `string4` | 采样流量 / 0.350～1.500L/min(赛默飞) | cshtml 标签 |
| `string5` | 机内温度 / 8～47℃(赛默飞) | cshtml 标签 |
| `string6` | 光室温度 / 47～51℃(赛默飞) | cshtml 标签 |
| `string7` | 斜率(Slope) / 0.500～2.000(赛默飞) | cshtml 标签 |
| `string8` | 截距(Offset) / ＞-15(赛默飞) | cshtml 标签 |
| `devicecode` | 仪器编号： / 使用满量程（PPM） | cshtml 标签 |
| `mcledtdate` | 满量程的80％ | cshtml 标签 |
| `mclsdtdate` | 满量程的80％ | cshtml 标签 |
| `ldshowvalue` | 零点 | cshtml 标签 |
| `lingdianppm` | 零点 | cshtml 标签 |
| `mclhowvalue` | 满量程的80％ | cshtml 标签 |
| `calibrationdate` | 校准日期 / 使用满量程（PPM） | cshtml 标签 |
| `ldbiaodingvalue` | 零点 | cshtml 标签 |
| `lingdianedtdate` | 零点 | cshtml 标签 |
| `lingdiansdtdate` | 零点 | cshtml 标签 |
| `mclbiaodingvalue` | 满量程的80％ | cshtml 标签 |

**平台校验器：**`devicecode`=required；`ldbiaodingvalue`=required；`ldshowvalue`=required；`lingdianppm`=required；`mclbiaodingvalue`=required；`mclhowvalue`=required；`mclppm`=required；`mpa`=required；`ppb`=required；`ppm`=required；`ppmcode`=required；`string1`=required；`string2`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required


## Sup_RF_CO2MulityPointCheck_Q（sup_rf_co2mulitypointcheck_q）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_CO2MulityPointCheck_Q`、视图 `Sup_RF_CO2MulityPointCheck_Q.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `ju` | 多点线性校准结果 | cshtml 标签 |
| `xl` | 多点线性校准结果 | cshtml 标签 |
| `ppb` | 仪器编号： / 使用量程（PPB） | cshtml 标签 |
| `ppm` | 标气瓶编号 / 标气浓度（PPM） | cshtml 标签 |
| `xgxs` | 多点线性校准结果 | cshtml 标签 |
| `xzjg` | 校准结果（合格/不合格） | cshtml 标签 |
| `ldcode` | 零气源型号 / 零气源编号 | cshtml 标签 |
| `jzqcode` | 校准器型号 / 校准器编号 | cshtml 标签 |
| `ldmodel` | 零气源型号 / 零气源编号 | cshtml 标签 |
| `mclbz10` | 满量程的10％ | cshtml 标签 |
| `mclbz20` | 满量程的20％ | cshtml 标签 |
| `mclbz40` | 满量程的40％ | cshtml 标签 |
| `mclbz60` | 满量程的60％ | cshtml 标签 |
| `mclbz80` | 满量程的80％ | cshtml 标签 |
| `mclxy10` | 满量程的10％ | cshtml 标签 |
| `mclxy20` | 满量程的20％ | cshtml 标签 |
| `mclxy40` | 满量程的40％ | cshtml 标签 |
| `mclxy60` | 满量程的60％ | cshtml 标签 |
| `mclxy80` | 满量程的80％ | cshtml 标签 |
| `ppmcode` | 标气瓶编号 / 标气浓度（PPM） | cshtml 标签 |
| `jzqmodel` | 校准器型号 / 校准器编号 | cshtml 标签 |
| `mclby101` | 满量程的10％ | cshtml 标签 |
| `mclby102` | 满量程的10％ | cshtml 标签 |
| `mclby201` | 满量程的20％ | cshtml 标签 |
| `mclby202` | 满量程的20％ | cshtml 标签 |
| `mclby401` | 满量程的40％ | cshtml 标签 |
| `mclby402` | 满量程的40％ | cshtml 标签 |
| `mclby601` | 满量程的60％ | cshtml 标签 |
| `mclby602` | 满量程的60％ | cshtml 标签 |
| `mclby801` | 满量程的80％ | cshtml 标签 |
| `mclby802` | 满量程的80％ | cshtml 标签 |
| `lingdianbz` | 零点 | cshtml 标签 |
| `lingdianxy` | 零点 | cshtml 标签 |
| `devicecode1` | 仪器编号： / 使用量程（PPB） | cshtml 标签 |
| `lingdianby1` | 零点 | cshtml 标签 |
| `lingdianby2` | 零点 | cshtml 标签 |
| `ppmcodedate` | 标气瓶有效期 | cshtml 标签 |
| `devicemodel1` | 监测仪器名称： / 校准日期 | cshtml 标签 |
| `mcledtdate10` | 满量程的10％ | cshtml 标签 |
| `mcledtdate20` | 满量程的20％ | cshtml 标签 |
| `mcledtdate40` | 满量程的40％ | cshtml 标签 |
| `mcledtdate60` | 满量程的60％ | cshtml 标签 |
| `mcledtdate80` | 满量程的80％ | cshtml 标签 |
| `mclsdtdate10` | 满量程的10％ | cshtml 标签 |
| `mclsdtdate20` | 满量程的20％ | cshtml 标签 |
| `mclsdtdate40` | 满量程的40％ | cshtml 标签 |
| `mclsdtdate60` | 满量程的60％ | cshtml 标签 |
| `mclsdtdate80` | 满量程的80％ | cshtml 标签 |
| `calibrationdate` | 监测仪器名称： / 校准日期 | cshtml 标签 |
| `lingdianedtdate` | 零点 | cshtml 标签 |
| `lingdiansdtdate` | 零点 | cshtml 标签 |

**平台校验器：**`devicecode1`=required；`devicemodel1`=required；`jzqcode`=required；`jzqmodel`=required；`ldcode`=required；`ldmodel`=required；`lingdianbz`=required；`mclbz10`=required；`mclbz20`=required；`mclbz40`=required；`mclbz60`=required；`mclbz80`=required；`ppb`=required；`ppm`=required；`ppmcode`=required


## Sup_RF_Calibration（sup_rf_calibration_noy）
- 源码依据：实体 `Sup_RF_Calibration_NOy`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `string28` | Nox斜率 | 实体注释 |
| `string29` | Nox截距 | 实体注释 |
| `string30` | NO斜率 | 实体注释 |
| `string31` | NO截距 | 实体注释 |


## Sup_RF_ChannelFlowCalibration（sup_rf_channelflowcalibration）
- 源码依据：实体 `Sup_RF_ChannelFlowCalibration`、视图 `Sup_RF_ChannelFlowCalibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `snsd` | 室内温度 / 室内湿度 | cshtml 标签 |
| `snwd` | 室内温度 / 室内湿度 | cshtml 标签 |
| `tb2xh` | （视图标签：OCEC） | 实体注释 |
| `tb3jj` | （视图标签：斜率 / 截距 / R2 / 斜率 / 截距 / R2） | 实体注释 |
| `tb3r2` | （视图标签：斜率 / 截距 / R2 / 斜率 / 截距 / R2） | 实体注释 |
| `tb3xl` | （视图标签：斜率 / 截距 / R2 / 斜率 / 截距 / R2） | 实体注释 |
| `tb4jj` | （视图标签：斜率 / 截距 / R2） | 实体注释 |
| `tb4r2` | （视图标签：斜率 / 截距 / R2） | 实体注释 |
| `tb4xl` | （视图标签：斜率 / 截距 / R2） | 实体注释 |
| `tb5jj` | （视图标签：斜率 / 截距 / R2） | 实体注释 |
| `tb5r2` | （视图标签：斜率 / 截距 / R2） | 实体注释 |
| `tb5xl` | （视图标签：斜率 / 截距 / R2） | 实体注释 |
| `tb6jj` | （视图标签：斜率 / 截距 / R2） | 实体注释 |
| `tb6r2` | （视图标签：斜率 / 截距 / R2） | 实体注释 |
| `tb6xl` | （视图标签：斜率 / 截距 / R2） | 实体注释 |
| `tb1bh1` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1bh2` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1jj1` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1jj2` | （视图标签：相关系数） | 实体注释 |
| `tb1xh1` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1xh2` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1xl1` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1xl2` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb3ck1` | （视图标签：0） | 实体注释 |
| `tb3ck2` | （视图标签：100） | 实体注释 |
| `tb3ck3` | （视图标签：85） | 实体注释 |
| `tb3ck4` | （视图标签：50） | 实体注释 |
| `tb3ck5` | （视图标签：30） | 实体注释 |
| `tb3ck6` | （视图标签：20） | 实体注释 |
| `tb3dy1` | （视图标签：0） | 实体注释 |
| `tb3dy2` | （视图标签：100） | 实体注释 |
| `tb3dy3` | （视图标签：85） | 实体注释 |
| `tb3dy4` | （视图标签：50） | 实体注释 |
| `tb3dy5` | （视图标签：30） | 实体注释 |
| `tb3dy6` | （视图标签：20） | 实体注释 |
| `tb3xz1` | （视图标签：0） | 实体注释 |
| `tb3xz2` | （视图标签：100） | 实体注释 |
| `tb3xz3` | （视图标签：85） | 实体注释 |
| `tb3xz4` | （视图标签：50） | 实体注释 |
| `tb3xz5` | （视图标签：30） | 实体注释 |
| `tb3xz6` | （视图标签：20） | 实体注释 |
| `tb4ck1` | （视图标签：0） | 实体注释 |
| `tb4ck2` | （视图标签：90） | 实体注释 |
| `tb4ck3` | （视图标签：60） | 实体注释 |
| `tb4ck4` | （视图标签：40） | 实体注释 |
| `tb4ck5` | （视图标签：25） | 实体注释 |
| `tb4ck6` | （视图标签：10） | 实体注释 |
| `tb4dy1` | （视图标签：0） | 实体注释 |
| `tb4dy2` | （视图标签：90） | 实体注释 |
| `tb4dy3` | （视图标签：60） | 实体注释 |
| `tb4dy4` | （视图标签：40） | 实体注释 |
| `tb4dy5` | （视图标签：25） | 实体注释 |
| `tb4dy6` | （视图标签：10） | 实体注释 |
| `tb4xz1` | （视图标签：0） | 实体注释 |
| `tb4xz2` | （视图标签：90） | 实体注释 |
| `tb4xz3` | （视图标签：60） | 实体注释 |
| `tb4xz4` | （视图标签：40） | 实体注释 |
| `tb4xz5` | （视图标签：25） | 实体注释 |
| `tb4xz6` | （视图标签：10） | 实体注释 |
| `tb5ck1` | （视图标签：0） | 实体注释 |
| `tb5ck2` | （视图标签：75） | 实体注释 |
| `tb5ck3` | （视图标签：45） | 实体注释 |
| `tb5ck4` | （视图标签：25） | 实体注释 |
| `tb5ck5` | （视图标签：12） | 实体注释 |
| `tb5ck6` | （视图标签：7） | 实体注释 |
| `tb5dy1` | （视图标签：0） | 实体注释 |
| `tb5dy2` | （视图标签：75） | 实体注释 |
| `tb5dy3` | （视图标签：45） | 实体注释 |
| `tb5dy4` | （视图标签：25） | 实体注释 |
| `tb5dy5` | （视图标签：12） | 实体注释 |
| `tb5dy6` | （视图标签：7） | 实体注释 |
| `tb5xz1` | （视图标签：0） | 实体注释 |
| `tb5xz2` | （视图标签：75） | 实体注释 |
| `tb5xz3` | （视图标签：45） | 实体注释 |
| `tb5xz4` | （视图标签：25） | 实体注释 |
| `tb5xz5` | （视图标签：12） | 实体注释 |
| `tb5xz6` | （视图标签：7） | 实体注释 |
| `tb6ck1` | （视图标签：0） | 实体注释 |
| `tb6ck2` | （视图标签：70） | 实体注释 |
| `tb6ck3` | （视图标签：50） | 实体注释 |
| `tb6ck4` | （视图标签：30） | 实体注释 |
| `tb6ck5` | （视图标签：15） | 实体注释 |
| `tb6ck6` | （视图标签：10） | 实体注释 |
| `tb6dy1` | （视图标签：0） | 实体注释 |
| `tb6dy2` | （视图标签：70） | 实体注释 |
| `tb6dy3` | （视图标签：50） | 实体注释 |
| `tb6dy4` | （视图标签：30） | 实体注释 |
| `tb6dy5` | （视图标签：15） | 实体注释 |
| `tb6dy6` | （视图标签：10） | 实体注释 |
| `tb6xz1` | （视图标签：0） | 实体注释 |
| `tb6xz2` | （视图标签：70） | 实体注释 |
| `tb6xz3` | （视图标签：50） | 实体注释 |
| `tb6xz4` | （视图标签：30） | 实体注释 |
| `tb6xz5` | （视图标签：15） | 实体注释 |
| `tb6xz6` | （视图标签：10） | 实体注释 |
| `tb2ccbh` | （视图标签：OCEC） | 实体注释 |
| `tb1xgxs1` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1xgxs2` |  | 实体注释 |
| `tb2sycjz` | （视图标签：OCEC） | 实体注释 |
| `tb2xycjz` | （视图标签：OCEC） | 实体注释 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `tb1sycjz1` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1sycjz2` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1xycjz1` | （视图标签：截距 / 相关系数） | 实体注释 |
| `tb1xycjz2` | （视图标签：截距 / 相关系数） | 实体注释 |
| `fixingflow` | R2 / 氦气 设定流量(cc/min） 参考流量计读数(cc/min） 参考流量计修正(cc/min） 操作 | cshtml 标签 |
| `readingflow` | R2 / 氦气 设定流量(cc/min） 参考流量计读数(cc/min） 参考流量计修正(cc/min） 操作 | cshtml 标签 |
| `settingflow` | 截距 / R2 | cshtml 标签 |
| `calibrationfactor1` | 校准系数： | cshtml 标签 |
| `calibrationfactor2` | 校准系数： | cshtml 标签 |
| `calibrationfactor3` | 校准系数： | cshtml 标签 |
| `calibrationfactor4` | 校准系数： | cshtml 标签 |

**平台校验器：**`calibrationfactor1`=required；`calibrationfactor2`=required；`calibrationfactor3`=required；`calibrationfactor4`=required；`snsd`=required；`snwd`=required；`tb1bh1`=required；`tb1bh2`=required；`tb1jj1`=required；`tb1jj2`=required；`tb1xgxs1`=required；`tb1xgxs2`=required；`tb1xh1`=required；`tb1xh2`=required；`tb1xl1`=required；`tb1xl2`=required；`tb2ccbh`=required；`tb2xh`=required；`tb3ck1`=required；`tb3ck2`=required；`tb3ck3`=required；`tb3ck4`=required；`tb3ck5`=required；`tb3ck6`=required；`tb3dy1`=required；`tb3dy2`=required；`tb3dy3`=required；`tb3dy4`=required；`tb3dy5`=required；`tb3dy6`=required；`tb3jj`=required；`tb3r2`=required；`tb3xl`=required；`tb3xz1`=required；`tb3xz2`=required；`tb3xz3`=required；`tb3xz4`=required；`tb3xz5`=required；`tb3xz6`=required；`tb4ck1`=required；`tb4ck2`=required；`tb4ck3`=required；`tb4ck4`=required；`tb4ck5`=required；`tb4ck6`=required；`tb4dy1`=required；`tb4dy2`=required；`tb4dy3`=required；`tb4dy4`=required；`tb4dy5`=required；`tb4dy6`=required；`tb4jj`=required；`tb4r2`=required；`tb4xl`=required；`tb4xz1`=required；`tb4xz2`=required；`tb4xz3`=required；`tb4xz4`=required；`tb4xz5`=required；`tb4xz6`=required；`tb5ck1`=required；`tb5ck2`=required；`tb5ck3`=required；`tb5ck4`=required；`tb5ck5`=required；`tb5ck6`=required；`tb5dy1`=required；`tb5dy2`=required；`tb5dy3`=required；`tb5dy4`=required；`tb5dy5`=required；`tb5dy6`=required；`tb5jj`=required；`tb5r2`=required；`tb5xl`=required；`tb5xz1`=required；`tb5xz2`=required；`tb5xz3`=required；`tb5xz4`=required；`tb5xz5`=required；`tb5xz6`=required；`tb6ck1`=required；`tb6ck2`=required；`tb6ck3`=required；`tb6ck4`=required；`tb6ck5`=required；`tb6ck6`=required；`tb6dy1`=required；`tb6dy2`=required；`tb6dy3`=required；`tb6dy4`=required；`tb6dy5`=required；`tb6dy6`=required；`tb6jj`=required；`tb6r2`=required；`tb6xl`=required；`tb6xz1`=required；`tb6xz2`=required；`tb6xz3`=required；`tb6xz4`=required；`tb6xz5`=required；`tb6xz6`=required


## Sup_RF_ChromatotecFlowCheck（sup_rf_chromatotecflowcheck）
- 源码依据：实体 `Sup_RF_ChromatotecFlowCheck`、视图 `Sup_RF_ChromatotecFlowCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `f_a` | 截距 / 相关系数 | cshtml 标签 |
| `f_b` | 截距 / 相关系数 | cshtml 标签 |
| `f_r` | （视图绑定，含义见标签） | cshtml 标签 |
| `f_code` | 截距 / 相关系数 | cshtml 标签 |
| `f_model` | 截距 / 相关系数 | cshtml 标签 |
| `humidity` | 温度 / 湿度 / 气压 | cshtml 标签 |
| `pressure` | 温度 / 湿度 / 气压 | cshtml 标签 |
| `c2c6_diff` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c2c6_isok` | 认证结果 | cshtml 标签 |
| `c2c6_fixed` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c2c6_scene` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c6c12_diff` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c6c12_isok` | 认证结果 | cshtml 标签 |
| `f_nextdate` | 截距 / 相关系数 | cshtml 标签 |
| `f_prevdate` | 截距 / 相关系数 | cshtml 标签 |
| `c2c6_target` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c6c12_fixed` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c6c12_scene` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `temperature` | 温度 / 湿度 / 气压 | cshtml 标签 |
| `c2c6_display` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c6c12_target` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c2c6_pressure` | （视图绑定，含义见标签） | cshtml 标签 |
| `c2c6_standard` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c6c12_display` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c6c12_pressure` | （视图绑定，含义见标签） | cshtml 标签 |
| `c6c12_standard` | 现场温度（℃） / 现场大气压（mmHg） | cshtml 标签 |
| `c2c6_temperature` | （视图绑定，含义见标签） | cshtml 标签 |
| `c6c12_temperature` | （视图绑定，含义见标签） | cshtml 标签 |

**平台校验器：**`c2c6_diff`=required,double；`c2c6_display`=required,double；`c2c6_fixed`=required,double；`c2c6_pressure`=required,double；`c2c6_scene`=required,double；`c2c6_standard`=required,double；`c2c6_target`=required,double；`c2c6_temperature`=required,double；`c6c12_diff`=required,double；`c6c12_display`=required,double；`c6c12_fixed`=required,double；`c6c12_pressure`=required,double；`c6c12_scene`=required,double；`c6c12_standard`=required,double；`c6c12_target`=required,double；`c6c12_temperature`=required,double；`f_a`=required,double；`f_b`=required,double；`f_code`=required；`f_model`=required；`f_r`=required,double；`humidity`=required,double；`pressure`=required,double；`temperature`=required,double


## Sup_RF_ChromatotecMonthMaintain（sup_rf_chromatotecmonthmaintain）
- 源码依据：实体 `Sup_RF_ChromatotecMonthMaintain`、视图 `Sup_RF_ChromatotecMonthMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remark_1` | 1 / H2压力核查 | cshtml 标签 |
| `remark_2` | 2 / Air压力核查 | cshtml 标签 |
| `remark_3` | 3 / 渗透管温度 | cshtml 标签 |
| `remark_4` | 4 / 采样流量核查(cc/min) | cshtml 标签 |
| `remark_5` | 5 / 渗透管流量核查(cc/min) | cshtml 标签 |
| `remark_6` | 6 / 渗透管总稀释流量核查(cc/min) | cshtml 标签 |
| `result_1` | 1 / H2压力核查 | cshtml 标签 |
| `result_2` | 2 / Air压力核查 | cshtml 标签 |
| `result_3` | 3 / 渗透管温度 | cshtml 标签 |
| `result_4` | 4 / 采样流量核查(cc/min) | cshtml 标签 |
| `result_5` | 5 / 渗透管流量核查(cc/min) | cshtml 标签 |
| `result_6` | 6 / 渗透管总稀释流量核查(cc/min) | cshtml 标签 |


## Sup_RF_ChromatotecQuarterMaintain（sup_rf_chromatotecquartermaintain）
- 源码依据：实体 `Sup_RF_ChromatotecQuarterMaintain`、视图 `Sup_RF_ChromatotecQuarterMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remark_1` | 1 / 炉温核查 | cshtml 标签 |
| `remark_2` | 2 / 脱附温度核查 | cshtml 标签 |
| `remark_3` | 3 / 零气流量核查(cc/min) | cshtml 标签 |
| `remark_4` | 4 / 标气流量核查(cc/min) | cshtml 标签 |
| `remark_5` | 5 / 清洗氢气发生器内部水箱 | cshtml 标签 |
| `remark_6` | 6 / 多点校准及方法检出限 | cshtml 标签 |
| `remark_7` | 1 / FID检测器喷嘴 | cshtml 标签 |
| `remark_8` | 7 / 全流程验漏检查 | cshtml 标签 |
| `result_1` | 1 / 炉温核查 | cshtml 标签 |
| `result_2` | 2 / 脱附温度核查 | cshtml 标签 |
| `result_3` | 3 / 零气流量核查(cc/min) | cshtml 标签 |
| `result_4` | 4 / 标气流量核查(cc/min) | cshtml 标签 |
| `result_5` | 5 / 清洗氢气发生器内部水箱 | cshtml 标签 |
| `result_6` | 6 / 多点校准及方法检出限 | cshtml 标签 |
| `result_7` | 1 / FID检测器喷嘴 | cshtml 标签 |
| `result_8` | 7 / 全流程验漏检查 | cshtml 标签 |


## Sup_RF_ChromatotecWeekCheck（sup_rf_chromatotecweekcheck）
- 源码依据：实体 `Sup_RF_ChromatotecWeekCheck`、视图 `Sup_RF_ChromatotecWeekCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `fid_c2c6` | 9 / FID信号值 | cshtml 标签 |
| `fid_c6c12` | 9 / FID信号值 | cshtml 标签 |
| `hi_remark` | 9 / 制氢电流值（mA） | cshtml 标签 |
| `hv_remark` | 10 / 制氢电压值（V） | cshtml 标签 |
| `fid_remark` | 9 / FID信号值 | cshtml 标签 |
| `hi_content` | 9 / 制氢电流值（mA） | cshtml 标签 |
| `hv_content` | 10 / 制氢电压值（V） | cshtml 标签 |
| `pr2_remark` | 2 / PR2阀压力（2bar） | cshtml 标签 |
| `pr3_remark` | 3 / PR3阀压力（3bar） | cshtml 标签 |
| `pr2_content` | 2 / PR2阀压力（2bar） | cshtml 标签 |
| `pr3_content` | 3 / PR3阀压力（3bar） | cshtml 标签 |
| `temp36_c2c6` | 4 / 炉温是否降到36℃ | cshtml 标签 |
| `tempok_c2c6` | 5 / 升温过程是否平稳 | cshtml 标签 |
| `dryflow_c2c6` | 11 / 干燥管反吹流量 | cshtml 标签 |
| `temp202_c2c6` | 6 / 炉温是否升到202℃ | cshtml 标签 |
| `temp36_c6c12` | 4 / 炉温是否降到36℃ | cshtml 标签 |
| `tempfid_c2c6` | 8 / FID温度波动范围 / (169.5-170.5℃) | cshtml 标签 |
| `tempok_c6c12` | 5 / 升温过程是否平稳 | cshtml 标签 |
| `temp200_c6c12` | 7 / 炉温是否升到200℃ | cshtml 标签 |
| `temp36_remark` | 4 / 炉温是否降到36℃ | cshtml 标签 |
| `temp40_remark` | 1 / 渗透炉温度（40℃） | cshtml 标签 |
| `tempcold_c2c6` | 10 / 冷堆温度（℃） | cshtml 标签 |
| `tempfid_c6c12` | 8 / FID温度波动范围 / (169.5-170.5℃) | cshtml 标签 |
| `tempok_remark` | 5 / 升温过程是否平稳 | cshtml 标签 |
| `dryflow_remark` | 11 / 干燥管反吹流量 | cshtml 标签 |
| `temp200_remark` | 7 / 炉温是否升到200℃ | cshtml 标签 |
| `temp202_remark` | 6 / 炉温是否升到202℃ | cshtml 标签 |
| `temp40_content` | 1 / 渗透炉温度（40℃） | cshtml 标签 |
| `pressure36_c2c6` | 3 / 36℃时柱压（hpa） | cshtml 标签 |
| `tempcold_remark` | 10 / 冷堆温度（℃） | cshtml 标签 |
| `tempoven_remark` | 2 / OVEN 温度（℃） | cshtml 标签 |
| `pressure36_c6c12` | 3 / 36℃时柱压（hpa） | cshtml 标签 |
| `samplflow_remark` | 4 / 采样流量（ml） | cshtml 标签 |
| `tempoven_content` | 2 / OVEN 温度（℃） | cshtml 标签 |
| `devicestatus_c2c6` | 1 / 仪器状态 | cshtml 标签 |
| `pressure36_remark` | 3 / 36℃时柱压（hpa） | cshtml 标签 |
| `pressurediff_c2c6` | 2 / 采样压差（hpa） | cshtml 标签 |
| `samplflow_content` | 4 / 采样流量（ml） | cshtml 标签 |
| `devicestatus_c6c12` | 1 / 仪器状态 | cshtml 标签 |
| `h_pressure_content` | 8 / 氢气发生器输出压力 / （2000mbar） | cshtml 标签 |
| `pressurediff_c6c12` | 2 / 采样压差（hpa） | cshtml 标签 |
| `tempmsinlet_remark` | 1 / MS Inlet 温度（摄氏度） | cshtml 标签 |
| `addpurewater_remark` | 11 / 是否添加纯水 | cshtml 标签 |
| `devicestatus_remark` | 1 / 仪器状态 | cshtml 标签 |
| `pressurediff_remark` | 2 / 采样压差（hpa） | cshtml 标签 |
| `tempmsinlet_content` | 1 / MS Inlet 温度（摄氏度） | cshtml 标签 |
| `zeroairpumpp_remark` | 4 / 零气泵压力（bar） | cshtml 标签 |
| `addpurewater_content` | 11 / 是否添加纯水 | cshtml 标签 |
| `zeroairpumpp4_remark` | 5 / 零气泵分压（4bar） | cshtml 标签 |
| `zeroairpumpp_content` | 4 / 零气泵压力（bar） | cshtml 标签 |
| `zeroairpumpp4_content` | 5 / 零气泵分压（4bar） | cshtml 标签 |
| `temptransferline_remark` | 3 / Transfer line温度（℃） | cshtml 标签 |
| `temptransferline_content` | 3 / Transfer line温度（℃） | cshtml 标签 |
| `zeroairpumpvalveoff_remark` | 6 / 零气泵排水阀 | cshtml 标签 |
| `zeroairpumpvalveoff_content` | 6 / 零气泵排水阀 | cshtml 标签 |
| `zeroairpumpvalvestart_remark` | 7 / 零气泵启动阀 | cshtml 标签 |
| `zeroairpumpvalvestart_content` | 7 / 零气泵启动阀 | cshtml 标签 |

**平台校验器：**`dryflow_c2c6`=required,double；`fid_c2c6`=required,double；`fid_c6c12`=required,double；`hi_content`=required,double；`hv_content`=required,double；`pressure36_c2c6`=required,double；`pressure36_c6c12`=required,double；`pressurediff_c2c6`=required,double；`pressurediff_c6c12`=required,double；`samplflow_content`=required,double；`tempcold_c2c6`=required,double；`tempmsinlet_content`=required,double；`tempoven_content`=required,double；`temptransferline_content`=required,double；`zeroairpumpp_content`=required,double


## Sup_RF_Co2Analyzerinspection_HalfYear（sup_rf_co2analyzerinspection）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_Co2Analyzerinspection`、视图 `Sup_RF_Co2Analyzerinspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `benchpr` | BENCH 温度(℃) / 40-59 | cshtml 标签 |
| `fcdrift` | 流量检查 / 季度 | cshtml 标签 |
| `pcdrift` | 压力检查 | cshtml 标签 |
| `tcdrift` | 温度检查 | cshtml 标签 |
| `ccrvalue` | 最小二乘法校准曲线 / 斜率b ： / 截距a ： / 相关系数 r： | cshtml 标签 |
| `formtype` | 表单类型 周 季 半年 | 实体注释 |
| `zpcdrift` | 零点检查 / 周 | cshtml 标签 |
| `fcendtime` | 流量检查 / 季度 | cshtml 标签 |
| `inttemppr` | 内部温度(℃) / 8.0-47 | cshtml 标签 |
| `pcendtime` | 压力检查 | cshtml 标签 |
| `spandrift` | 跨度检查 | cshtml 标签 |
| `tcendtime` | 温度检查 | cshtml 标签 |
| `fcsetvalue` | 流量检查 / 季度 | cshtml 标签 |
| `pcsetvalue` | 压力检查 | cshtml 标签 |
| `pressurepr` | 压力（mmHg） / 250-1000 | cshtml 标签 |
| `tcsetvalue` | 温度检查 | cshtml 标签 |
| `zpcendtime` | 零点检查 / 周 | cshtml 标签 |
| `automaticpr` | 自动增益强度（Hz） / 150000-300000 | cshtml 标签 |
| `fcstarttime` | 流量检查 / 季度 | cshtml 标签 |
| `pcstarttime` | 压力检查 | cshtml 标签 |
| `slopebvalue` | 最小二乘法校准曲线 / 斜率b ： / 截距a ： / 相关系数 r： | cshtml 标签 |
| `spanendtime` | 跨度检查 | cshtml 标签 |
| `tcstarttime` | 温度检查 | cshtml 标签 |
| `zpcsetvalue` | 零点检查 / 周 | cshtml 标签 |
| `atisitnormal` | 气密性 / 是否正常 / 半年 | cshtml 标签 |
| `ecisitnormal` | 外部清洁 / 是否正常 | cshtml 标签 |
| `fmisitnormal` | 滤膜 / 是否更换 / 按需 | cshtml 标签 |
| `fullscale0az` | 零点 | cshtml 标签 |
| `fullscale0re` | 零点 | cshtml 标签 |
| `fullscale0sg` | 零点 | cshtml 标签 |
| `icisitnormal` | 内部清洁 / 是否正常 | cshtml 标签 |
| `motorspeedpr` | 电机转速 / 100% | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `pmisitnormal` | 泵膜 / 是否更换 | cshtml 标签 |
| `sgisitnormal` | 标气 / 是否更换 | cshtml 标签 |
| `spansetvalue` | 跨度检查 | cshtml 标签 |
| `zpcstarttime` | 零点检查 / 周 | cshtml 标签 |
| `biasvoltagepr` | 偏置电压（V） / (-120) - (-100) | cshtml 标签 |
| `fullscale10az` | 满量程的 10% | cshtml 标签 |
| `fullscale10re` | 满量程的 10% | cshtml 标签 |
| `fullscale10sg` | 满量程的 10% | cshtml 标签 |
| `fullscale20az` | 满量程的 20% | cshtml 标签 |
| `fullscale20re` | 满量程的 20% | cshtml 标签 |
| `fullscale20sg` | 满量程的 20% | cshtml 标签 |
| `fullscale30az` | 满量程的 30% | cshtml 标签 |
| `fullscale30re` | 满量程的 30% | cshtml 标签 |
| `fullscale30sg` | 满量程的 30% | cshtml 标签 |
| `fullscale40az` | 满量程的 40% | cshtml 标签 |
| `fullscale40re` | 满量程的 40% | cshtml 标签 |
| `fullscale40sg` | 满量程的 40% | cshtml 标签 |
| `fullscale50az` | 满量程的 50% | cshtml 标签 |
| `fullscale50re` | 满量程的 50% | cshtml 标签 |
| `fullscale50sg` | 满量程的 50% | cshtml 标签 |
| `fullscale60az` | 满量程的 60% | cshtml 标签 |
| `fullscale60re` | 满量程的 60% | cshtml 标签 |
| `fullscale60sg` | 满量程的 60% | cshtml 标签 |
| `fullscale70az` | 满量程的 70% | cshtml 标签 |
| `fullscale70re` | 满量程的 70% | cshtml 标签 |
| `fullscale70sg` | 满量程的 70% | cshtml 标签 |
| `fullscale80az` | 满量程的 80% | cshtml 标签 |
| `fullscale80re` | 满量程的 80% | cshtml 标签 |
| `fullscale80sg` | 满量程的 80% | cshtml 标签 |
| `fullscale90az` | 满量程的 90% | cshtml 标签 |
| `fullscale90re` | 满量程的 90% | cshtml 标签 |
| `fullscale90sg` | 满量程的 90% | cshtml 标签 |
| `gpcisitnormal` | 气路清洁 / 是否正常 | cshtml 标签 |
| `spanstarttime` | 跨度检查 | cshtml 标签 |
| `fcdisplayvalue` | 流量检查 / 季度 | cshtml 标签 |
| `pcdisplayvalue` | 压力检查 | cshtml 标签 |
| `samplingflowpr` | 采样流量（L/min） / 0.350-1.500 | cshtml 标签 |
| `tcdisplayvalue` | 温度检查 | cshtml 标签 |
| `automaticcvalue` | 自动增益强度（Hz） / 150000-300000 | cshtml 标签 |
| `benchcheckvalue` | BENCH 温度(℃) / 40-59 | cshtml 标签 |
| `fullscale0etime` | 零点 | cshtml 标签 |
| `fullscale0stime` | 零点 | cshtml 标签 |
| `interceptavalue` | 最小二乘法校准曲线 / 斜率b ： / 截距a ： / 相关系数 r： | cshtml 标签 |
| `zpcdisplayvalue` | 零点检查 / 周 | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `fcisitcalibrated` | 流量检查 / 季度 | cshtml 标签 |
| `fullscale10etime` | 满量程的 10% | cshtml 标签 |
| `fullscale10stime` | 满量程的 10% | cshtml 标签 |
| `fullscale20etime` | 满量程的 20% | cshtml 标签 |
| `fullscale20stime` | 满量程的 20% | cshtml 标签 |
| `fullscale30etime` | 满量程的 30% | cshtml 标签 |
| `fullscale30stime` | 满量程的 30% | cshtml 标签 |
| `fullscale40etime` | 满量程的 40% | cshtml 标签 |
| `fullscale40stime` | 满量程的 40% | cshtml 标签 |
| `fullscale50etime` | 满量程的 50% | cshtml 标签 |
| `fullscale50stime` | 满量程的 50% | cshtml 标签 |
| `fullscale60etime` | 满量程的 60% | cshtml 标签 |
| `fullscale60stime` | 满量程的 60% | cshtml 标签 |
| `fullscale70etime` | 满量程的 70% | cshtml 标签 |
| `fullscale70stime` | 满量程的 70% | cshtml 标签 |
| `fullscale80etime` | 满量程的 80% | cshtml 标签 |
| `fullscale80stime` | 满量程的 80% | cshtml 标签 |
| `fullscale90etime` | 满量程的 90% | cshtml 标签 |
| `fullscale90stime` | 满量程的 90% | cshtml 标签 |
| `motorspeedcvalue` | 电机转速 / 100% | cshtml 标签 |
| `pcisitcalibrated` | 压力检查 | cshtml 标签 |
| `spandisplayvalue` | 跨度检查 | cshtml 标签 |
| `tcisitcalibrated` | 温度检查 | cshtml 标签 |
| `biasvoltagecvalue` | 偏置电压（V） / (-120) - (-100) | cshtml 标签 |
| `inttempcheckvalue` | 内部温度(℃) / 8.0-47 | cshtml 标签 |
| `zpcisitcalibrated` | 零点检查 / 周 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |
| `pressurecheckvalue` | 压力（mmHg） / 250-1000 | cshtml 标签 |
| `samplingflowcvalue` | 采样流量（L/min） / 0.350-1.500 | cshtml 标签 |
| `spanisitcalibrated` | 跨度检查 | cshtml 标签 |


## Sup_RF_DailyInspection（sup_rf_dailyinspection）
- 源码依据：实体 `Sup_RF_DailyInspection`、视图 `Sup_RF_DailyInspection.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 1 / 仪器状态 / 有无报警 | cshtml 标签 |
| `bool_2` | 2 / FID点火状态 / / | cshtml 标签 |
| `bool_3` | 3 / 数据采集及上传 / / | cshtml 标签 |
| `bool_4` | 4 / 采样泵状态检查 / / | cshtml 标签 |
| `bool_5` | 5 / 氢空一体机状态 / 有无报警 | cshtml 标签 |
| `bool_6` | 9 / 采样总管风机 / / | cshtml 标签 |
| `bool_7` | 10 / 采样总管加热装置 / / | cshtml 标签 |
| `bool_8` | 11 / 采样管路是否有冷凝水、是否洁净 / / | cshtml 标签 |
| `bool_9` | 1 / 干燥剂/变色硅胶 / / | cshtml 标签 |
| `bool_10` | 2 / 氢气发生器纯水 / / | cshtml 标签 |
| `bool_11` | 3 / 颗粒物过滤膜 / / | cshtml 标签 |
| `remark1` | 1 / 仪器状态 / 有无报警 | cshtml 标签 |
| `remark2` | 2 / FID点火状态 / / | cshtml 标签 |
| `remark3` | 3 / 数据采集及上传 / / | cshtml 标签 |
| `remark4` | 4 / 采样泵状态检查 / / | cshtml 标签 |
| `remark5` | 5 / 氢空一体机状态 / 有无报警 | cshtml 标签 |
| `remark6` | 6 / 零气加热温度 / 400℃ | cshtml 标签 |
| `remark7` | 7 / 零气输出压力 / 不低于0.35Mpa （不低于50psi） | cshtml 标签 |
| `remark8` | 8 / 氢气输出压力 / 不低于0.35Mpa （不低于50psi） | cshtml 标签 |
| `remark9` | 9 / 采样总管风机 / / | cshtml 标签 |
| `remarks` | 备注 | cshtml 标签 |
| `string1` | 6 / 零气加热温度 / 400℃ | cshtml 标签 |
| `string2` | 7 / 零气输出压力 / 不低于0.35Mpa （不低于50psi） | cshtml 标签 |
| `string3` | 8 / 氢气输出压力 / 不低于0.35Mpa （不低于50psi） | cshtml 标签 |
| `remark10` | 10 / 采样总管加热装置 / / | cshtml 标签 |
| `remark11` | 11 / 采样管路是否有冷凝水、是否洁净 / / | cshtml 标签 |
| `remark12` | 1 / 干燥剂/变色硅胶 / / | cshtml 标签 |
| `remark13` | 2 / 氢气发生器纯水 / / | cshtml 标签 |
| `remark14` | 3 / 颗粒物过滤膜 / / | cshtml 标签 |
| `abnormalremark` | 异常情况处理记录 | cshtml 标签 |


## Sup_RF_DeviceFlowCheck（sup_rf_deviceflowcheck）
- 源码依据：实体 `Sup_RF_DeviceFlowCheck`、视图 `Sup_RF_DeviceFlowCheck.cshtml`、Vue 移植版 x4

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `r1` | " }) / " }) | cshtml 标签 |
| `error1` | 校准前 | cshtml 标签 |
| `error2` | 校准后 | cshtml 标签 |
| `slope1` | 截距 / 相关系数 | cshtml 标签 |
| `intercept1` | 相关系数 / " }) | cshtml 标签 |
| `coefficient` | （视图绑定，含义见标签） | cshtml 标签 |
| `flowercode1` | 截距 / 相关系数 | cshtml 标签 |
| `devicevalue1` | 校准前 | cshtml 标签 |
| `devicevalue2` | 校准后 | cshtml 标签 |
| `flowermodel1` | 截距 / 相关系数 | cshtml 标签 |
| `iscalibrate1` | 校准前 | cshtml 标签 |
| `iscalibrate2` | 校准后 | cshtml 标签 |
| `iscalibrate4` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `targetvalue1` | 校准前 | cshtml 标签 |
| `targetvalue2` | 校准后 | cshtml 标签 |
| `curveequation` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `displayvalue1` | 校准前 | cshtml 标签 |
| `displayvalue2` | 校准后 | cshtml 标签 |
| `setflowvalue1` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `setflowvalue2` | 是 否 | cshtml 标签 |
| `setflowvalue3` | 是 否 | cshtml 标签 |
| `setflowvalue4` | （视图绑定，含义见标签） | cshtml 标签 |
| `setflowvalue5` | （视图绑定，含义见标签） | cshtml 标签 |
| `relativeerror1` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `relativeerror2` | 是 否 | cshtml 标签 |
| `relativeerror3` | （视图绑定，含义见标签） | cshtml 标签 |
| `relativeerror4` | （视图绑定，含义见标签） | cshtml 标签 |
| `relativeerror5` | （视图绑定，含义见标签） | cshtml 标签 |
| `actualflowvalue1` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `actualflowvalue2` | 是 否 | cshtml 标签 |
| `actualflowvalue3` | （视图绑定，含义见标签） | cshtml 标签 |
| `actualflowvalue4` | （视图绑定，含义见标签） | cshtml 标签 |
| `actualflowvalue5` | （视图绑定，含义见标签） | cshtml 标签 |
| `correctionvalue1` | 校准前 | cshtml 标签 |
| `correctionvalue2` | 校准后 | cshtml 标签 |
| `indicationerror1` | 校准前 | cshtml 标签 |
| `indicationerror2` | 校准后 | cshtml 标签 |
| `calibratedatenext1` | 截距 / 相关系数 | cshtml 标签 |
| `calibratedateprev1` | 截距 / 相关系数 | cshtml 标签 |

**平台校验器：**`actualflowvalue1`=required；`actualflowvalue2`=required；`actualflowvalue3`=required；`actualflowvalue4`=required；`actualflowvalue5`=required；`coefficient`=required；`correctionvalue1`=required；`correctionvalue2`=required；`curveequation`=required；`devicevalue1`=required；`devicevalue2`=required；`displayvalue1`=required；`displayvalue2`=required；`error1`=required；`error2`=required；`flowercode1`=required；`flowercode2`=required；`flowermodel1`=required；`flowermodel2`=required；`intercept1`=required；`intercept2`=required；`liquidactualflowvalue1`=required；`liquidactualflowvalue2`=required；`liquidactualflowvalue3`=required；`liquidflowsetvalue`=required；`liquidflowstandarddeviation`=required；`r1`=required；`r2`=required；`relativeerror1`=required；`relativeerror2`=required；`relativeerror3`=required；`relativeerror4`=required；`relativeerror5`=required；`setflowvalue1`=required；`setflowvalue2`=required；`setflowvalue3`=required；`setflowvalue4`=required；`setflowvalue5`=required；`slope1`=required；`slope2`=required；`targetvalue1`=required；`targetvalue2`=required


## Sup_RF_DeviceFlowCheck_PTRMS（sup_rf_deviceflowcheck）
- 《组分仪器工单规则》：光化学组分/PTR-MS.docx
- 源码依据：实体 `Sup_RF_DeviceFlowCheck`、视图 `Sup_RF_DeviceFlowCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `r1` | " }) / " }) | cshtml 标签 |
| `error1` | 校准前 | cshtml 标签 |
| `error2` | 校准后 | cshtml 标签 |
| `slope1` | 截距 / 相关系数 | cshtml 标签 |
| `intercept1` | 相关系数 / " }) | cshtml 标签 |
| `coefficient` | （视图绑定，含义见标签） | cshtml 标签 |
| `flowercode1` | 截距 / 相关系数 | cshtml 标签 |
| `devicevalue1` | 校准前 | cshtml 标签 |
| `devicevalue2` | 校准后 | cshtml 标签 |
| `flowermodel1` | 截距 / 相关系数 | cshtml 标签 |
| `iscalibrate1` | 校准前 | cshtml 标签 |
| `iscalibrate2` | 校准后 | cshtml 标签 |
| `iscalibrate4` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `targetvalue1` | 校准前 | cshtml 标签 |
| `targetvalue2` | 校准后 | cshtml 标签 |
| `curveequation` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `displayvalue1` | 校准前 | cshtml 标签 |
| `displayvalue2` | 校准后 | cshtml 标签 |
| `setflowvalue1` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `setflowvalue2` | 是 否 | cshtml 标签 |
| `setflowvalue3` | 是 否 | cshtml 标签 |
| `setflowvalue4` | （视图绑定，含义见标签） | cshtml 标签 |
| `setflowvalue5` | （视图绑定，含义见标签） | cshtml 标签 |
| `relativeerror1` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `relativeerror2` | 是 否 | cshtml 标签 |
| `relativeerror3` | （视图绑定，含义见标签） | cshtml 标签 |
| `relativeerror4` | （视图绑定，含义见标签） | cshtml 标签 |
| `relativeerror5` | （视图绑定，含义见标签） | cshtml 标签 |
| `actualflowvalue1` | 曲线方程/ 相关系数 / 是否合格 | cshtml 标签 |
| `actualflowvalue2` | 是 否 | cshtml 标签 |
| `actualflowvalue3` | （视图绑定，含义见标签） | cshtml 标签 |
| `actualflowvalue4` | （视图绑定，含义见标签） | cshtml 标签 |
| `actualflowvalue5` | （视图绑定，含义见标签） | cshtml 标签 |
| `correctionvalue1` | 校准前 | cshtml 标签 |
| `correctionvalue2` | 校准后 | cshtml 标签 |
| `indicationerror1` | 校准前 | cshtml 标签 |
| `indicationerror2` | 校准后 | cshtml 标签 |
| `calibratedatenext1` | 截距 / 相关系数 | cshtml 标签 |
| `calibratedateprev1` | 截距 / 相关系数 | cshtml 标签 |

**平台校验器：**`actualflowvalue1`=required；`actualflowvalue2`=required；`actualflowvalue3`=required；`actualflowvalue4`=required；`actualflowvalue5`=required；`coefficient`=required；`correctionvalue1`=required；`correctionvalue2`=required；`curveequation`=required；`devicevalue1`=required；`devicevalue2`=required；`displayvalue1`=required；`displayvalue2`=required；`error1`=required；`error2`=required；`flowercode1`=required；`flowercode2`=required；`flowermodel1`=required；`flowermodel2`=required；`intercept1`=required；`intercept2`=required；`liquidactualflowvalue1`=required；`liquidactualflowvalue2`=required；`liquidactualflowvalue3`=required；`liquidflowsetvalue`=required；`liquidflowstandarddeviation`=required；`r1`=required；`r2`=required；`relativeerror1`=required；`relativeerror2`=required；`relativeerror3`=required；`relativeerror4`=required；`relativeerror5`=required；`setflowvalue1`=required；`setflowvalue2`=required；`setflowvalue3`=required；`setflowvalue4`=required；`setflowvalue5`=required；`slope1`=required；`slope2`=required；`targetvalue1`=required；`targetvalue2`=required


## Sup_RF_DiaphragmCheck（sup_rf_common）
- 源码依据：实体 `Sup_RF_DiaphragmCheck`、视图 `Sup_RF_DiaphragmCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `string1` | 温度（视图标签：温度 / 湿度） | 实体注释 |
| `string2` | 湿度（视图标签：温度 / 湿度） | 实体注释 |
| `string3` | 仪器名称（视图标签：仪器型号 / 仪器序列号） | 实体注释 |
| `string4` | 仪器型号（视图标签：仪器型号 / 仪器序列号） | 实体注释 |
| `string5` | 仪器序列号（视图标签：仪器型号 / 仪器序列号） | 实体注释 |
| `string6` | EC1 - 膜名称（视图标签：EC1 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string7` | EC1 - 标准浓度（视图标签：EC1 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string8` | EC1 - 测量浓度1（视图标签：EC1 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string9` | EC1 - 偏差1（视图标签：EC1 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string10` | EC1 - 测量浓度2 | 实体注释 |
| `string11` | EC1 - 偏差2 | 实体注释 |
| `string12` | EC1 - 测量浓度3 | 实体注释 |
| `string13` | EC1 - 偏差3 | 实体注释 |
| `string14` | EC1 - 测量浓度 - 平均值 | 实体注释 |
| `string15` | EC1 - 偏差 - 平均值 | 实体注释 |
| `string16` | EC2 - 膜名称（视图标签：EC2 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string17` | EC2 - 标准浓度（视图标签：EC2 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string18` | EC2 - 测量浓度1（视图标签：EC2 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string19` | EC2 - 偏差1（视图标签：EC2 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string20` | EC2 - 测量浓度2 | 实体注释 |
| `string21` | EC2 - 偏差2 | 实体注释 |
| `string22` | EC2 - 测量浓度3 | 实体注释 |
| `string23` | EC2 - 偏差3 | 实体注释 |
| `string24` | EC2 - 测量浓度 - 平均值 | 实体注释 |
| `string25` | EC2 - 偏差 - 平均值 | 实体注释 |
| `string26` | EC3 - 膜名称（视图标签：EC3 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string27` | EC3 - 标准浓度（视图标签：EC3 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string28` | EC3 - 测量浓度1（视图标签：EC3 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string29` | EC3 - 偏差1（视图标签：EC3 / 膜名称： / 标准浓度： / 1） | 实体注释 |
| `string30` | EC3 - 测量浓度2 | 实体注释 |
| `string31` | EC3 - 偏差2 | 实体注释 |
| `string32` | EC3 - 测量浓度3 | 实体注释 |
| `string33` | EC3 - 偏差3 | 实体注释 |
| `string34` | EC3 - 测量浓度 - 平均值 | 实体注释 |
| `string35` | EC3 - 偏差 - 平均值 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_EquipmentMaintenance（sup_rf_equipmentmaintenance）
- 源码依据：实体 `Sup_RF_EquipmentMaintenance`、视图 `Sup_RF_EquipmentMaintenance.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `date1` | 流量稳定性 / ≤±10% | cshtml 标签 |
| `date2` | 流量稳定性 / ≤±10% | cshtml 标签 |
| `date3` | （视图绑定，含义见标签） | cshtml 标签 |
| `date4` | （视图绑定，含义见标签） | cshtml 标签 |
| `date5` | （视图绑定，含义见标签） | cshtml 标签 |
| `date6` | （视图绑定，含义见标签） | cshtml 标签 |
| `atdate` | 气密性 / 流量≤0.005L/min | cshtml 标签 |
| `fsdate` | 流量稳定性 / ≤±10% | cshtml 标签 |
| `rpdate` | 蠕动泵泵管卡位更换 / 每两周更换一次泵管卡位或 更换新的泵管 | cshtml 标签 |
| `pfsdate` | 配制甲醛标液 / 每月打开一瓶新的甲醛溶液 并配制好甲醛标液 （放置于冰箱中密封保存） | cshtml 标签 |
| `remarks` | 备注 | cshtml 标签 |
| `projects1` | 流量稳定性 / ≤±10% | cshtml 标签 |
| `projects2` | ≤±10% | cshtml 标签 |
| `projects3` | （视图绑定，含义见标签） | cshtml 标签 |
| `projects4` | （视图绑定，含义见标签） | cshtml 标签 |
| `projects5` | （视图绑定，含义见标签） | cshtml 标签 |
| `projects6` | （视图绑定，含义见标签） | cshtml 标签 |
| `normalrange1` | 流量稳定性 / ≤±10% | cshtml 标签 |
| `normalrange2` | （视图绑定，含义见标签） | cshtml 标签 |
| `normalrange3` | （视图绑定，含义见标签） | cshtml 标签 |
| `normalrange4` | （视图绑定，含义见标签） | cshtml 标签 |
| `normalrange5` | （视图绑定，含义见标签） | cshtml 标签 |
| `normalrange6` | （视图绑定，含义见标签） | cshtml 标签 |
| `measuredvalue1` | 配制甲醛标液 / 每月打开一瓶新的甲醛溶液 并配制好甲醛标液 （放置于冰箱中密封保存） | cshtml 标签 |
| `measuredvalue2` | 蠕动泵泵管卡位更换 / 每两周更换一次泵管卡位或 更换新的泵管 | cshtml 标签 |
| `measuredvalue3` | 气密性 / 流量≤0.005L/min | cshtml 标签 |
| `measuredvalue4` | 流量稳定性 / ≤±10% | cshtml 标签 |
| `measuredvalue5` | 流量稳定性 / ≤±10% | cshtml 标签 |
| `measuredvalue6` | （视图绑定，含义见标签） | cshtml 标签 |
| `measuredvalue7` | （视图绑定，含义见标签） | cshtml 标签 |
| `measuredvalue8` | （视图绑定，含义见标签） | cshtml 标签 |
| `measuredvalue9` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord1` | 流量稳定性 / ≤±10% | cshtml 标签 |
| `abnormalrecord2` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord3` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord4` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord5` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord6` | （视图绑定，含义见标签） | cshtml 标签 |
| `measuredvalue10` | （视图绑定，含义见标签） | cshtml 标签 |
| `atabnormalrecord` | 气密性 / 流量≤0.005L/min | cshtml 标签 |
| `fsabnormalrecord` | 流量稳定性 / ≤±10% | cshtml 标签 |
| `rpabnormalrecord` | 蠕动泵泵管卡位更换 / 每两周更换一次泵管卡位或 更换新的泵管 | cshtml 标签 |
| `pfsabnormalrecord` | 配制甲醛标液 / 每月打开一瓶新的甲醛溶液 并配制好甲醛标液 （放置于冰箱中密封保存） | cshtml 标签 |

**平台校验器：**`string10`=required；`string11`=required；`string14`=required；`string15`=required；`string16`=required；`string19`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_EquipmentStatus（sup_rf_equipmentstatus）
- 源码依据：实体 `Sup_RF_EquipmentStatus`、视图 `Sup_RF_EquipmentStatus.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 1 / 仪器状态 / / | cshtml 标签 |
| `bool_2` | 2 / 捕集温度 / 检查冷藏箱温度及冷凝循环水 | cshtml 标签 |
| `bool_3` | 8 / 零点校准 / 每天执行两次 | cshtml 标签 |
| `bool_4` | 9 / 采样总管风机 / / | cshtml 标签 |
| `bool_5` | 10 / 采样总管加热装置 / / | cshtml 标签 |
| `bool_6` | 11 / 采样管路是否有冷凝水、是否洁净 / / | cshtml 标签 |
| `bool_7` | 1 / 吸收液余量 / 液面应不低于500ml | cshtml 标签 |
| `bool_8` | 2 / 反应液余量 / 液面应不低于500ml | cshtml 标签 |
| `bool_9` | 3 / 废液情况 / 不超过废液桶容积的80% | cshtml 标签 |
| `bool_10` | 4 / 泵管卡位替换（SP14、15） / 每两周替换一次 | cshtml 标签 |
| `bool_11` | 5 / 颗粒物过滤膜 / 每周更换一次 | cshtml 标签 |
| `bool_12` | 6 / 针式过滤器 / 每周更换一次 | cshtml 标签 |
| `remark1` | 1 / 仪器状态 / / | cshtml 标签 |
| `remark2` | 2 / 捕集温度 / 检查冷藏箱温度及冷凝循环水 | cshtml 标签 |
| `remark3` | 3 / 反应温度 / 70±0.2℃ | cshtml 标签 |
| `remark4` | 4 / 检测温度 / 35±0.2℃ | cshtml 标签 |
| `remark5` | 5 / 采样流量 / 0.7L/min | cshtml 标签 |
| `remark6` | 6 / 液体1流量 / 0.45-0.55ml/min | cshtml 标签 |
| `remark7` | 7 / 液体2流量 / 0.22-0.26ml/min | cshtml 标签 |
| `remark8` | 8 / 零点校准 / 每天执行两次 | cshtml 标签 |
| `remark9` | 9 / 采样总管风机 / / | cshtml 标签 |
| `string1` | 3 / 反应温度 / 70±0.2℃ | cshtml 标签 |
| `string2` | 4 / 检测温度 / 35±0.2℃ | cshtml 标签 |
| `string3` | 5 / 采样流量 / 0.7L/min | cshtml 标签 |
| `string4` | 6 / 液体1流量 / 0.45-0.55ml/min | cshtml 标签 |
| `string5` | 7 / 液体2流量 / 0.22-0.26ml/min | cshtml 标签 |
| `string6` | 7 / 液体流量 / ＞0.3ml/min | cshtml 标签 |
| `string7` | 8 / 蠕动泵转速 / 默认为10r/min | cshtml 标签 |
| `remark10` | 10 / 采样总管加热装置 / / | cshtml 标签 |
| `remark11` | 11 / 采样管路是否有冷凝水、是否洁净 / / | cshtml 标签 |
| `remark12` | 1 / 吸收液余量 / 液面应不低于500ml | cshtml 标签 |
| `remark13` | 2 / 反应液余量 / 液面应不低于500ml | cshtml 标签 |
| `remark14` | 3 / 废液情况 / 不超过废液桶容积的80% | cshtml 标签 |
| `remark15` | 4 / 泵管卡位替换（SP14、15） / 每两周替换一次 | cshtml 标签 |
| `remark16` | 5 / 颗粒物过滤膜 / 每周更换一次 | cshtml 标签 |
| `remark17` | 6 / 针式过滤器 / 每周更换一次 | cshtml 标签 |


## Sup_RF_GACMonthMaintain（sup_rf_gacmonthmaintain）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_GACMonthMaintain`、视图 `Sup_RF_GACMonthMaintain.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `pm25result` | 1 / 清洗切割器 | cshtml 标签 |
| `iconeresult` | 4 / IC单向阀清洁 | cshtml 标签 |
| `icsixresult` | 2 / 清洗扩散管 | cshtml 标签 |
| `pm25remarks` | 1 / 清洗切割器 | cshtml 标签 |
| `aersolresult` | 3 / 清洗冷凝瓶 | cshtml 标签 |
| `iconeremarks` | 4 / IC单向阀清洁 | cshtml 标签 |
| `icsixremarks` | 2 / 清洗扩散管 | cshtml 标签 |
| `aersolremarks` | 3 / 清洗冷凝瓶 | cshtml 标签 |
| `anionvremarks` | 2 / 阴阳离子分析柱垫片更换 | cshtml 标签 |
| `kongbairesult` | 4 / 系统空白核查 | cshtml 标签 |
| `kongbairemarks` | 4 / 系统空白核查 | cshtml 标签 |
| `zhengqueduresult` | 5 / 正确度核查 | cshtml 标签 |
| `zhengqueduremarks` | 5 / 正确度核查 | cshtml 标签 |
| `anionprotectresult` | 1 / 色谱柱更换 | cshtml 标签 |
| `anionanalysisresult` | 2 / 阴阳离子分析柱垫片更换 | cshtml 标签 |
| `anionprotectremarks` | 1 / 色谱柱更换 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_GACMonthMaintain_WaterSolubleIons.vue）：**

bool_1 至 bool_5、string1 至 string5 为月度维护结果和备注； bool_6、string6 为色谱柱更换结果和备注；commonFile 为附件。 原表没有自动计算或必填 validator。新建记录的单选默认第二项，与旧 bool 默认值一致。


## Sup_RF_GACQuarterMaintain（sup_rf_gacquartermaintain）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_GACQuarterMaintain`、视图 `Sup_RF_GACQuarterMaintain.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `icresult` | 4 / IC定量环清洗 | cshtml 标签 |
| `gasresult` | 3 / GAS收集器清洗 | cshtml 标签 |
| `ic2result` | 5 / IC进样管路清洁 | cshtml 标签 |
| `icremarks` | 4 / IC定量环清洗 | cshtml 标签 |
| `gasremarks` | 3 / GAS收集器清洗 | cshtml 标签 |
| `ic2remarks` | 5 / IC进样管路清洁 | cshtml 标签 |
| `aersolresult` | 2 / AERSOL收集器清洗 | cshtml 标签 |
| `aersolremarks` | 2 / AERSOL收集器清洗 | cshtml 标签 |
| `denuderresult` | 1 / DENUDER管清洗 | cshtml 标签 |
| `denuderremarks` | 1 / DENUDER管清洗 | cshtml 标签 |
| `anioneluentresult` | 1 / 阴/阳离子淋洗液 | cshtml 标签 |
| `anioneluentresult2` | 1 / 阴/阳离子淋洗液 | cshtml 标签 |
| `anionanalyticalresult` | 2 / 阴/阳离子分析柱 | cshtml 标签 |
| `anionprotectiveresult` | 3 / 阴/阳离子保护柱 | cshtml 标签 |
| `anionanalyticalresult2` | 2 / 阴/阳离子分析柱 | cshtml 标签 |
| `anionprotectiveresult2` | 3 / 阴/阳离子保护柱 | cshtml 标签 |


## Sup_RF_GACWeekMaintain（sup_rf_gacweekmaintain）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_GACWeekMaintain`、视图 `Sup_RF_GACWeekMaintain.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `gasresult` | 4 / GAS进样量 （标注刻度线） | cshtml 标签 |
| `gasremarks` | 4 / GAS进样量 （标注刻度线） | cshtml 标签 |
| `aersolresult` | 3 / Aersol进样量 （标注刻度线） | cshtml 标签 |
| `aersol2result` | 6 / Aersol冷凝管积液检查 | cshtml 标签 |
| `aersolremarks` | 3 / Aersol进样量 （标注刻度线） | cshtml 标签 |
| `denuderresult` | 5 / Denuder管液面 （标注刻度线） | cshtml 标签 |
| `aersol2remarks` | 6 / Aersol冷凝管积液检查 | cshtml 标签 |
| `denuderremarks` | 5 / Denuder管液面 （标注刻度线） | cshtml 标签 |
| `micropumpresult` | 7 / 微量泵工作状态 | cshtml 标签 |
| `filterheadresult` | 1 / 阴阳离子色谱过滤头 | cshtml 标签 |
| `micropumpremarks` | 7 / 微量泵工作状态 | cshtml 标签 |
| `ultrawaterresult` | 3 / 超纯水 | cshtml 标签 |
| `anioncolumnresult` | 8 / 阴离子柱流量（4mm：0.5-0.75ml/min） | cshtml 标签 |
| `anioneluentresult` | 6 / 阴离子淋洗液剩余量（10-100%） | cshtml 标签 |
| `anionicwaterpeak1` | 9 / 阴离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `anionicwaterpeak2` | 9 / 阴离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `filterheadremarks` | 1 / 阴阳离子色谱过滤头 | cshtml 标签 |
| `ultrawaterremarks` | 3 / 超纯水 | cshtml 标签 |
| `anioncolumnremarks` | 8 / 阴离子柱流量（4mm：0.5-0.75ml/min） | cshtml 标签 |
| `anioneluentremarks` | 6 / 阴离子淋洗液剩余量（10-100%） | cshtml 标签 |
| `cationcolumnresult` | 4 / 阳离子柱流量（4mm：0.5-0.75ml/min） | cshtml 标签 |
| `samplingflowresult` | 8 / 采样流量 | cshtml 标签 |
| `anionpressureresult` | 5 / 阴离子柱压 （4mm：3-6.5 psi） | cshtml 标签 |
| `cationcolumnremarks` | 4 / 阳离子柱流量（4mm：0.5-0.75ml/min） | cshtml 标签 |
| `samplingflowremarks` | 8 / 采样流量 | cshtml 标签 |
| `anionpressureremarks` | 5 / 阴离子柱压 （4mm：3-6.5 psi） | cshtml 标签 |
| `cationiceluentresult` | 2 / 阳离子淋洗液剩余量（0-100%） | cshtml 标签 |
| `cationpressureresult` | 1 / 阳离子柱压 （4mm：2.5-5.5 psi） | cshtml 标签 |
| `steamgeneratorresult` | 2 / 蒸汽发生器温度 （280℃-320℃） | cshtml 标签 |
| `anionsuppressorresult` | 7 / 阴离子抑制器电流（15-35mA） | cshtml 标签 |
| `cationiceluentremarks` | 2 / 阳离子淋洗液剩余量（0-100%） | cshtml 标签 |
| `cationpressureremarks` | 1 / 阳离子柱压 （4mm：2.5-5.5 psi） | cshtml 标签 |
| `steamgeneratorremarks` | 2 / 蒸汽发生器温度 （280℃-320℃） | cshtml 标签 |
| `aersolfilterheadresult` | 2 / AERSOL过滤头 | cshtml 标签 |
| `anionsuppressorremarks` | 7 / 阴离子抑制器电流（15-35mA） | cshtml 标签 |
| `cationsuppressorresult` | 3 / 阳离子抑制器电流（15-35mA） | cshtml 标签 |
| `instrumentstatusresult` | 1 / 仪器状态 | cshtml 标签 |
| `aersolfilterheadremarks` | 2 / AERSOL过滤头 | cshtml 标签 |
| `anionicwaterpeakremarks` | 9 / 阴离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `cationsuppressorremarks` | 3 / 阳离子抑制器电流（15-35mA） | cshtml 标签 |
| `instrumentstatusremarks` | 1 / 仪器状态 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_GACWeekMaintain_WaterSolubleIons.vue）：**

bool_1 至 bool_7 为运行检查；string1 至 string7 为对应备注。 string8 至 string23 为 IC 离子色谱的结果及备注；bool_8 至 bool_10、string24 至 string26 为耗材配件更换记录。 commonFile 为附件。原表没有计算逻辑和必填 validator。


## Sup_RF_GACWeekMaintainByMARGA（sup_rf_gacweekmaintainbymarga）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_GACWeekMaintainByMARGA`、视图 `Sup_RF_GACWeekMaintainByMARGA.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remarks` | 备注： | cshtml 标签 |
| `wrdresult` | 2 / WRD液膜 / 均无断层 | cshtml 标签 |
| `wrdremarks` | 2 / WRD液膜 / 均无断层 | cshtml 标签 |
| `br_aerremarks` | 阴离子内标系数Br - | cshtml 标签 |
| `br_gasremarks` | 阴离子内标系数Br - | cshtml 标签 |
| `denuderresult` | 预防性维护（每年） / Denuder管密封圈（每年） | cshtml 标签 |
| `li_aerremarks` | 阳离子气溶胶内标系数Li + | cshtml 标签 |
| `li_gasremarks` | 阳离子气溶胶内标系数Li + | cshtml 标签 |
| `rergasremarks` | 6 / 气溶胶样品（Aer） / 气体样品（Gas） / 0.9-1.1之间 | cshtml 标签 |
| `washsysresult` | 冲洗系统（每季度） / 阳离子分析柱（每半年） | cshtml 标签 |
| `pumppiperesult` | 内标液（5L/每月） / 蠕动泵管（每半年） | cshtml 标签 |
| `filterateresult` | 阳离子淋洗液（10L/每3周） / 在线过滤（3个/每2月） | cshtml 标签 |
| `pumppipe2result` | 再生液（5L/每月） / 蠕动泵管（每半年） | cshtml 标签 |
| `filterheadresult` | 阴离子淋洗液（10L/每3周） / 滤头（每周） | cshtml 标签 |
| `anioncolumnresult` | 吸收液（20L/每周） / 阴离子分析柱（每半年） | cshtml 标签 |
| `anioneluentresult` | 阴离子淋洗液（10L/每3周） / 滤头（每周） | cshtml 标签 |
| `sixwayvalveresult` | 六通阀清洗（每半年） / 保护柱滤芯（2个/每月） | cshtml 标签 |
| `cationcolumnresult` | 冲洗系统（每季度） / 阳离子分析柱（每半年） | cshtml 标签 |
| `cationeluentresult` | 阳离子淋洗液（10L/每3周） / 在线过滤（3个/每2月） | cshtml 标签 |
| `anionpressureresult` | 10 / 阴离子柱压 / 4-5Mpa，具体压力需结合分析柱、柱流速等参数 | cshtml 标签 |
| `anionvelocityresult` | 9 / 阴离子柱流速（ml/min） | cshtml 标签 |
| `filterelementresult` | 六通阀清洗（每半年） / 保护柱滤芯（2个/每月） | cshtml 标签 |
| `anionpressureremarks` | 10 / 阴离子柱压 / 4-5Mpa，具体压力需结合分析柱、柱流速等参数 | cshtml 标签 |
| `anionvelocityremarks` | 9 / 阴离子柱流速（ml/min） | cshtml 标签 |
| `cationpressureresult` | 13 / 阳离子柱压 / 7-9Mpa，具体压力需结合分析柱、柱流速等参数 | cshtml 标签 |
| `cationvelocityresult` | 12 / 阳离子柱流速（ml/min） | cshtml 标签 |
| `steamgeneratorresult` | 3 / 蒸汽发生器工作状况 / 120℃±10℃ | cshtml 标签 |
| `anionconductionresult` | 8 / 阴离子电导 / 4μs/cm（±1μS/cm） | cshtml 标签 |
| `cationpressureremarks` | 13 / 阳离子柱压 / 7-9Mpa，具体压力需结合分析柱、柱流速等参数 | cshtml 标签 |
| `cationvelocityremarks` | 12 / 阳离子柱流速（ml/min） | cshtml 标签 |
| `steamgeneratorremarks` | 3 / 蒸汽发生器工作状况 / 120℃±10℃ | cshtml 标签 |
| `absorptionliquidresult` | 吸收液（20L/每周） / 阴离子分析柱（每半年） | cshtml 标签 |
| `anionconductionremarks` | 8 / 阴离子电导 / 4μs/cm（±1μS/cm） | cshtml 标签 |
| `cationconductionresult` | 11 / 阳离子电导 / 1400μs/cm（±50μS/cm） | cshtml 标签 |
| `instrumentstatusresult` | 1 / 仪器状态 | cshtml 标签 |
| `internalstandardresult` | 内标液（5L/每月） / 蠕动泵管（每半年） | cshtml 标签 |
| `cationconductionremarks` | 11 / 阳离子电导 / 1400μs/cm（±50μS/cm） | cshtml 标签 |
| `instrumentleakageresult` | 5 / 仪器有无漏液情况 | cshtml 标签 |
| `instrumentstatusremarks` | 1 / 仪器状态 | cshtml 标签 |
| `instrumentleakageremarks` | 5 / 仪器有无漏液情况 | cshtml 标签 |
| `regenerativeliquidresult` | 再生液（5L/每月） / 蠕动泵管（每半年） | cshtml 标签 |
| `samplingpumpstatusresult` | 7 / 采样泵工作状态 / 无明显异响，可正常触发启动 | cshtml 标签 |
| `samplingpumpstatusremarks` | 7 / 采样泵工作状态 / 无明显异响，可正常触发启动 | cshtml 标签 |
| `steamgeneratorliquidresult` | 4 / 蒸汽发生器补液泵工作状况 / 无卡死状况，平滑转动 | cshtml 标签 |
| `preventivemaintenanceresult` | 预防性维护（每年） / Denuder管密封圈（每年） | cshtml 标签 |
| `steamgeneratorliquidremarks` | 4 / 蒸汽发生器补液泵工作状况 / 无卡死状况，平滑转动 | cshtml 标签 |

**平台校验器：**`anionconductionresult`=required；`anionpressureresult`=required；`anionvelocityresult`=required；`br_aerremarks`=required；`br_gasremarks`=required；`cationconductionresult`=required；`cationpressureresult`=required；`cationvelocityresult`=required；`filterheadresult`=required；`li_aerremarks`=required；`li_gasremarks`=required


## Sup_RF_GACYearMaintain（sup_rf_gacyearmaintain）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_GACYearMaintain`、视图 `Sup_RF_GACYearMaintain.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `icresult` | 2 / IC全系统清洁 | cshtml 标签 |
| `gacresult` | 3 / GAC前处理全系统清洁 | cshtml 标签 |
| `icremarks` | 2 / IC全系统清洁 | cshtml 标签 |
| `gacremarks` | 3 / GAC前处理全系统清洁 | cshtml 标签 |
| `samplingresult` | 1 / 采样管清洁 | cshtml 标签 |
| `samplingremarks` | 1 / 采样管清洁 | cshtml 标签 |
| `filterelementresult` | 1 / 超纯水机滤芯更换 | cshtml 标签 |
| `filterelementremarks` | 1 / 超纯水机滤芯更换 | cshtml 标签 |
| `filtermembraneresult` | 2 / 超纯水机过滤膜更换 | cshtml 标签 |
| `filtermembraneremarks` | 2 / 超纯水机过滤膜更换 | cshtml 标签 |


## Sup_RF_HCHOCollectPercent（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/甲醛.docx
- 源码依据：实体 `Sup_RF_HCHOCollectPercent`、视图 `Sup_RF_HCHOCollectPercent.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 测试日期（视图标签：出厂编号 / 测试日期） | 实体注释 |
| `time2` | 测试时间1 | 实体注释 |
| `time3` | 测试时间2 | 实体注释 |
| `time4` | 3 | cshtml 标签 |
| `string1` | 测试地点 | 实体注释 |
| `string2` | 生产商 | 实体注释 |
| `string3` | 出厂编号 | 实体注释 |
| `string4` | 气体流量 | 实体注释 |
| `string5` | 液体流量 | 实体注释 |
| `string6` | 甲醛标气发生值 | 实体注释 |
| `string7` | 甲醛气体测定值-1 | 实体注释 |
| `string8` | 测定均值 | 实体注释 |
| `string11` | 甲醛气体测定值2 | 实体注释 |
| `string12` |  | 实体注释 |
| `string43` | 捕集效率/% | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_HCHODetectionLimit（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/甲醛.docx
- 源码依据：实体 `Sup_RF_HCHODetectionLimit`、视图 `Sup_RF_HCHODetectionLimit.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：出厂编号 / 测试日期） | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `string1` | 测试地点 | 实体注释 |
| `string2` | 生产商 | 实体注释 |
| `string3` | 出厂编号 | 实体注释 |
| `string4` | 气体流量 | 实体注释 |
| `string5` | 液体流量 | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string31` | 检出限/ppt | 实体注释 |
| `string32` | 检出限/ppt | cshtml 标签 |
| `string33` | 检出限/ppt | cshtml 标签 |
| `string34` | 噪声/ppb | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_HCHOMLinearError（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/甲醛.docx
- 源码依据：实体 `Sup_RF_HCHOMLinearError`、视图 `Sup_RF_HCHOMLinearError.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 测试日期（视图标签：出厂编号 / 测试日期） | 实体注释 |
| `time2` | 测试时间1 | 实体注释 |
| `time3` | 2 | cshtml 标签 |
| `time4` | 3 | cshtml 标签 |
| `time5` | 4 | cshtml 标签 |
| `time6` | 5 | cshtml 标签 |
| `time7` | 6 | cshtml 标签 |
| `time8` | 7 | cshtml 标签 |
| `time9` | 8 | cshtml 标签 |
| `time10` | 9 | cshtml 标签 |
| `time11` | 10 | cshtml 标签 |
| `time12` | 11 | cshtml 标签 |
| `time13` | 12 | cshtml 标签 |
| `string1` | 测试地点 | 实体注释 |
| `string2` | 生产商 | 实体注释 |
| `string3` | 出厂编号 | 实体注释 |
| `string4` | 气体流量 | 实体注释 |
| `string5` | 液体流量 | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string43` | 单次最大线性误差(%) | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_HCHORepeatTest（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/甲醛.docx
- 源码依据：实体 `Sup_RF_HCHORepeatTest`、视图 `Sup_RF_HCHORepeatTest.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：出厂编号 / 测试日期） | 实体注释 |
| `time2` | 结束时间（视图标签：1） | 实体注释 |
| `time3` | 2 | cshtml 标签 |
| `time4` | 3 | cshtml 标签 |
| `time5` | 4 | cshtml 标签 |
| `time6` | 5 | cshtml 标签 |
| `time7` | 6 | cshtml 标签 |
| `string1` | 测试地点 | 实体注释 |
| `string2` | 生产商 | 实体注释 |
| `string3` | 出厂编号 | 实体注释 |
| `string4` | 气体流量 | 实体注释 |
| `string5` | 液体流量 | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string43` | 相对标准偏差/% | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_HONOConsumablesReplace（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/HONO.docx
- 源码依据：实体 `Sup_RF_HONOConsumablesReplace`、视图 `Sup_RF_HONOConsumablesReplace.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：维护单位 / 安装地点 / 维护时间） | 实体注释 |
| `time2` | 结束时间（视图标签：1） | 实体注释 |
| `time3` | 2 | cshtml 标签 |
| `time4` | 3 | cshtml 标签 |
| `time5` | 4 | cshtml 标签 |
| `time6` | 5 | cshtml 标签 |
| `string1` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string2` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string3` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string4` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string5` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string6` | 1 | cshtml 标签 |
| `string7` | 1 | cshtml 标签 |
| `string8` | 1 | cshtml 标签 |
| `string9` | 2 | cshtml 标签 |
| `remark50` | 备注： | cshtml 标签 |
| `string10` | 2 | cshtml 标签 |
| `string11` | 2 | cshtml 标签 |
| `string12` | 3 | cshtml 标签 |
| `string13` | 3 | cshtml 标签 |
| `string14` | 3 | cshtml 标签 |
| `string15` | 4 | cshtml 标签 |
| `string16` | 4 | cshtml 标签 |
| `string17` | 4 | cshtml 标签 |
| `string18` | 5 | cshtml 标签 |
| `string19` | 5 | cshtml 标签 |
| `string20` | 5 | cshtml 标签 |

**平台校验器：**`string1`=required；`string2`=required；`string3`=required；`string4`=required；`string5`=required


## Sup_RF_HP_Accuracy（sup_rf_common）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_HP_Accuracy`、视图 `Sup_RF_HP_Accuracy.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：开始时间 / 结束时间） | 实体注释 |
| `time2` | 结束时间（视图标签：开始时间 / 结束时间） | 实体注释 |
| `bool_1` | 审核结果 | cshtml 标签 |
| `string1` | 审核标气编号 | cshtml 标签 |
| `string2` | 审核标气编号 | cshtml 标签 |
| `string3` | 审核标气编号 | cshtml 标签 |
| `string4` | 审核标气编号 | cshtml 标签 |
| `string5` | 审核标气编号 | cshtml 标签 |
| `string6` | 审核标气编号 | cshtml 标签 |
| `string7` | 审核标气浓度值 Y | cshtml 标签 |
| `string8` | 审核标气浓度值 Y | cshtml 标签 |
| `string9` | 审核标气浓度值 Y | cshtml 标签 |
| `string10` | 审核标气浓度值 Y | cshtml 标签 |
| `string11` | 审核标气浓度值 Y | cshtml 标签 |
| `string12` | 审核标气浓度值 Y | cshtml 标签 |
| `string13` | 审核标气仪器响应浓度值 X | cshtml 标签 |
| `string14` | 审核标气仪器响应浓度值 X | cshtml 标签 |
| `string15` | 审核标气仪器响应浓度值 X | cshtml 标签 |
| `string16` | 审核标气仪器响应浓度值 X | cshtml 标签 |
| `string17` | 审核标气仪器响应浓度值 X | cshtml 标签 |
| `string18` | 审核标气仪器响应浓度值 X | cshtml 标签 |
| `string19` | 校准曲线 （Y=aX+b） | cshtml 标签 |
| `string20` | 校准曲线 （Y=aX+b） | cshtml 标签 |
| `string21` | 校准曲线 （Y=aX+b） | cshtml 标签 |
| `string22` | 站点工作气 / 编号 | cshtml 标签 |
| `string23` | 站点工作气 / 编号 | cshtml 标签 |
| `string24` | 标称浓度值 | cshtml 标签 |
| `string25` | 标称浓度值 | cshtml 标签 |
| `string26` | 响应浓度值 | cshtml 标签 |
| `string27` | 响应浓度值 | cshtml 标签 |
| `string28` | 修正浓度值 | cshtml 标签 |
| `string29` | 修正浓度值 | cshtml 标签 |
| `string30` | 差值 | cshtml 标签 |
| `string31` | 差值 | cshtml 标签 |


## Sup_RF_HP_Calibration（sup_rf_common）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_HP_Calibration`、视图 `Sup_RF_HP_Calibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `edt` | （视图绑定，含义见标签） | cshtml 标签 |
| `sdt` | （视图绑定，含义见标签） | cshtml 标签 |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `detail_str_1` | （视图绑定，含义见标签） | cshtml 标签 |
| `detail_str_2` | （视图绑定，含义见标签） | cshtml 标签 |
| `termofvalidity` | （视图绑定，含义见标签） | cshtml 标签 |


## Sup_RF_HP_Comparability（sup_rf_common）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_HP_Comparability`、视图 `Sup_RF_HP_Comparability.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：开始时间 / 结束时间） | 实体注释 |
| `time2` | 结束时间（视图标签：开始时间 / 结束时间） | 实体注释 |
| `bool_1` | 审核结果 | cshtml 标签 |
| `string1` | 校准方程 （Y=aX+b） | cshtml 标签 |
| `string2` | 校准方程 （Y=aX+b） | cshtml 标签 |
| `string3` | 校准方程 （Y=aX+b） | cshtml 标签 |
| `string4` | 站点工作气 / 编号 | cshtml 标签 |
| `string5` | 站点工作气 / 编号 | cshtml 标签 |
| `string6` | 标称浓度值 | cshtml 标签 |
| `string7` | 标称浓度值 | cshtml 标签 |
| `string8` | 响应浓度值 | cshtml 标签 |
| `string9` | 响应浓度值 | cshtml 标签 |
| `string10` | 审核标气编号 / 审核标气标称浓度值 | cshtml 标签 |
| `string11` | 审核标气编号 / 审核标气标称浓度值 | cshtml 标签 |
| `string12` | 审核标气响应浓度值 / 审核标气修正浓度值 | cshtml 标签 |
| `string13` | 审核标气响应浓度值 / 审核标气修正浓度值 | cshtml 标签 |
| `string14` | 审核标气差值 | cshtml 标签 |


## Sup_RF_HP_DalyHealth（sup_rf_common）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_HP_DalyHealth`、视图 `Sup_RF_HP_DalyHealth.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `edt` | （视图绑定，含义见标签） | cshtml 标签 |
| `sdt` | （视图绑定，含义见标签） | cshtml 标签 |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `edt_2_` | 是 否 | cshtml 标签 |
| `sdt_2_` | 是 否 | cshtml 标签 |
| `remark1` | 加热盒温度(Warn box Temp) / ℃ / 45±1 | cshtml 标签 |
| `remark2` | 腔室温度(Cavity Temp) / ℃ / 45±1 | cshtml 标签 |
| `remark3` | 腔室压力(Cavity Pressure) / Torr / 140±1 | cshtml 标签 |
| `remark4` | 激光发生器温度 / ℃ / - | cshtml 标签 |
| `remark5` | H2O 水汽值 / % / < 0.05% | cshtml 标签 |
| `remark6` | 系统软件工作状态 / - / - / 正常 不正常 | cshtml 标签 |
| `remark7` | 仪器与数采数据的一致性 / - / - / 正常 不正常 | cshtml 标签 |
| `remark8` | 时间校准 / 世界时 / ±30s | cshtml 标签 |
| `remark9` | 抽气泵泵膜、阀片检查 | cshtml 标签 |
| `string1` | 加热盒温度(Warn box Temp) / ℃ / 45±1 | cshtml 标签 |
| `string2` | 腔室温度(Cavity Temp) / ℃ / 45±1 | cshtml 标签 |
| `string3` | 腔室压力(Cavity Pressure) / Torr / 140±1 | cshtml 标签 |
| `string4` | 激光发生器温度 / ℃ / - | cshtml 标签 |
| `string5` | H2O 水汽值 / % / < 0.05% | cshtml 标签 |
| `string8` | 时间校准 / 世界时 / ±30s | cshtml 标签 |
| `remark10` | 气路正压部分气密性检查 | cshtml 标签 |
| `remark11` | 采样过滤器（入口、管路）检查 | cshtml 标签 |
| `remark12` | 颗粒物过滤膜检查 | cshtml 标签 |
| `remark13` | 室外采样管检查 | cshtml 标签 |
| `remark20` | 报警信息： | cshtml 标签 |
| `detail_str_1` | （视图绑定，含义见标签） | cshtml 标签 |
| `detail_str_2` | 是 否 | cshtml 标签 |
| `termofvalidity` | （视图绑定，含义见标签） | cshtml 标签 |


## Sup_RF_HP_Precision（sup_rf_common）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_HP_Precision`、视图 `Sup_RF_HP_Precision.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：开始时间 / 结束时间） | 实体注释 |
| `time2` | 结束时间（视图标签：开始时间 / 结束时间） | 实体注释 |
| `time3` | 标气标称浓度值 / 标气有效期 | cshtml 标签 |
| `bool_1` | 审核结果 | cshtml 标签 |
| `string1` | 标气来源 / 标气编号 | cshtml 标签 |
| `string2` | 标气来源 / 标气编号 | cshtml 标签 |
| `string3` | 标气标称浓度值 / 标气有效期 | cshtml 标签 |
| `string4` | 标准偏差 SD / 相对标准偏差 RSD | cshtml 标签 |
| `string5` | 标准偏差 SD / 相对标准偏差 RSD | cshtml 标签 |


## Sup_RF_HP_StationCheck（sup_rf_common）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_HP_StationCheck`、视图 `Sup_RF_HP_StationCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 1 / 点位周围环境变化情况 | cshtml 标签 |
| `bool_2` | 2 / 点位周围安全隐患 | cshtml 标签 |
| `bool_3` | 3 / 点位周围道路、供电线路、通讯线路、给排水设施完好或损坏状况 | cshtml 标签 |
| `bool_4` | 4 / 站房外围的防护栏、隔离带有无损坏情况 | cshtml 标签 |
| `bool_5` | 5 / 视频监控系统是否正常 | cshtml 标签 |
| `bool_6` | 6 / 周围树木是否需要修剪 | cshtml 标签 |
| `bool_7` | 7 / 站房防雷接地是否完好 | cshtml 标签 |
| `bool_8` | 8 / 站房屋顶是否完好，有无漏雨 | cshtml 标签 |
| `bool_9` | 9 / 仪器房外部采样管路是否正常，顶端过滤器是否脱落 | cshtml 标签 |
| `bool_10` | 10 / 采样设施（采样塔等）周围是否正常 | cshtml 标签 |
| `bool_11` | 1 / 站房内部的供电、通讯是否畅通 | cshtml 标签 |
| `bool_12` | 2 / 站房内部给排水、供暖设施、空调工作状况是否正常 | cshtml 标签 |
| `bool_13` | 3 / 各种消防、安全设施是否完好齐全 | cshtml 标签 |
| `bool_14` | 4 / 站房内有无气泵产生的异常声音 | cshtml 标签 |
| `bool_15` | 5 / 站房内有无异常气味 | cshtml 标签 |
| `bool_16` | 6 / 站房温度、湿度是否符合要求 | cshtml 标签 |
| `bool_17` | 7 / 气体采样管及支管是否由于室外温差产生冷凝水 | cshtml 标签 |
| `bool_18` | 8 / 站房排风扇是否正常运行 | cshtml 标签 |
| `bool_19` | 9 / 稳压电源参数是否正常 | cshtml 标签 |
| `bool_20` | 10 / 各电源插头、线板工作是否正常 | cshtml 标签 |
| `bool_21` | 11 / 仪器气泵工作是否正常 | cshtml 标签 |
| `bool_22` | 12 / Nafion 膜是否需更换（如有） | cshtml 标签 |
| `bool_23` | 13 / 气瓶减压阀压力指示是否正常 | cshtml 标签 |
| `bool_24` | 14 / 抽气泵采样流量是否正常 | cshtml 标签 |
| `bool_25` | 15 / 仪器进气总流量是否正常 | cshtml 标签 |
| `bool_26` | 16 / 站房内采样管气密性是否正常（通过 CO2 数据观察） | cshtml 标签 |
| `bool_27` | 17 / 多口阀当前阀位是否正确，切换是否正常 | cshtml 标签 |
| `bool_28` | 18 / 冷阱工作状态是否正常 | cshtml 标签 |
| `bool_29` | 19 / UPS 工作状态是否正常 | cshtml 标签 |


## Sup_RF_HY_NMHCMaintenanceRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/甲烷非甲烷.docx
- 源码依据：实体 `Sup_RF_HY_NMHCMaintenanceRecord`、视图 `Sup_RF_HY_NMHCMaintenanceRecord.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次校准日期（视图标签：零气流量计） | 实体注释 |
| `time2` | 参考流量计 - 下一次校准日期（视图标签：零气流量计） | 实体注释 |
| `time3` | OCEC分析仪资料 - 上一次校准时间 | 实体注释 |
| `time4` | OCEC分析仪资料 - 下一次校准时间 | 实体注释 |
| `bool_1` | 1 / 动态校准仪流量传递 / / | cshtml 标签 |
| `bool_2` | 2 / 采样总管清洁 / / | cshtml 标签 |
| `remark1` | 1 / 动态校准仪流量传递 / / | cshtml 标签 |
| `remark2` | 2 / 采样总管清洁 / / | cshtml 标签 |
| `string1` | 设备型号（视图标签：零气流量计） | 实体注释 |
| `string2` | 出厂编号（视图标签：零气流量计） | 实体注释 |
| `string3` | 斜率（视图标签：零气流量计） | 实体注释 |
| `string4` | 截距（视图标签：零气流量计） | 实体注释 |
| `string5` | 相关系数（视图标签：标气流量计） | 实体注释 |
| `string6` | 仪器型号（视图标签：标气流量计） | 实体注释 |
| `string7` | 出厂编号 | 实体注释 |
| `string8` | 监测项目 | 实体注释 |
| `string9` | 设定流量 - 氦气 | 实体注释 |
| `string10` | 显示流量 - 氦气 | 实体注释 |
| `string11` | 参考流量计读数 - 氦气 | 实体注释 |
| `string12` | 参考流量计修正 - 氦气 | 实体注释 |
| `string13` | 误差 - 氦气 | 实体注释 |
| `string14` | 检查结果 - 氦气 | 实体注释 |
| `string15` | 设定流量 - 氦气（吹扫） | 实体注释 |
| `string16` | 显示流量 - 氦气（吹扫） | 实体注释 |
| `string17` | 参考流量计读数 - 氦气（吹扫） | 实体注释 |
| `string18` | 参考流量计修正 - 氦气（吹扫） | 实体注释 |
| `string19` | 误差 - 氦气（吹扫） | 实体注释 |
| `string20` | 检查结果 - 氦气（吹扫） | 实体注释 |
| `string21` | 设定流量 - 氦氧 | 实体注释 |
| `string22` | 显示流量 - 氦氧 | 实体注释 |
| `string23` | 参考流量计读数 - 氦氧 | 实体注释 |
| `string24` | 参考流量计修正 - 氦氧 | 实体注释 |
| `string25` | 误差 - 氦氧 | 实体注释 |
| `string26` | 检查结果 - 氦氧 | 实体注释 |
| `string27` | 设定流量 - 氦甲烷 | 实体注释 |
| `string28` | 显示流量 - 氦甲烷 | 实体注释 |
| `string29` | 参考流量计读数 - 氦甲烷 | 实体注释 |
| `string30` | 参考流量计修正 - 氦甲烷 | 实体注释 |
| `string31` | 误差 - 氦甲烷 | 实体注释 |
| `string32` | 检查结果 - 氦甲烷 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_HalfYear_HONOCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/HONO.docx
- 源码依据：实体 `Sup_RF_HalfYear_HONOCheck`、视图 `Sup_RF_HalfYear_HONOCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：维护单位 / 安装地点 / 维护时间） | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 1 / 室外检查 / 室外取气盒固定是否牢固 | cshtml 标签 |
| `bool_2` | 循环水浴器温控及水位高度 | cshtml 标签 |
| `bool_3` | 取气盒循环水运行检查 | cshtml 标签 |
| `bool_4` | 取气盒管路连接 | cshtml 标签 |
| `bool_5` | 2 / 系统检查 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `bool_6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `bool_7` | 泵头转速是否正常 | cshtml 标签 |
| `bool_8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `bool_9` | 泵管卡子松紧度 | cshtml 标签 |
| `bool_10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `bool_11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `bool_12` | 安全瓶 / 无进液 | cshtml 标签 |
| `bool_13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `bool_14` | 光源LED / 正常光照 | cshtml 标签 |
| `bool_15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `bool_16` | 红色线是否达到预计值 | cshtml 标签 |
| `bool_17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `bool_18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `bool_19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `bool_20` | 测量数据偏离 | cshtml 标签 |
| `bool_21` | 是否存在异常数据 | cshtml 标签 |
| `bool_22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `bool_23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `bool_24` | R2避光保护 | cshtml 标签 |
| `bool_25` | 外表无破损 | cshtml 标签 |
| `bool_26` | 试剂 / 是否过期 | cshtml 标签 |
| `bool_27` | 配置是否准确 | cshtml 标签 |
| `bool_28` | 剩余量是否充足 | cshtml 标签 |
| `bool_29` | 空气过滤膜 / 检查是否需要更换 | cshtml 标签 |
| `remark1` | 1 / 室外检查 / 室外取气盒固定是否牢固 | cshtml 标签 |
| `remark2` | 循环水浴器温控及水位高度 | cshtml 标签 |
| `remark3` | 取气盒循环水运行检查 | cshtml 标签 |
| `remark4` | 取气盒管路连接 | cshtml 标签 |
| `remark5` | 2 / 系统检查 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `remark6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `remark7` | 泵头转速是否正常 | cshtml 标签 |
| `remark8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `remark9` | 泵管卡子松紧度 | cshtml 标签 |
| `string1` | 1 / 室外检查 / 室外取气盒固定是否牢固 | cshtml 标签 |
| `string2` | 循环水浴器温控及水位高度 | cshtml 标签 |
| `string3` | 取气盒循环水运行检查 | cshtml 标签 |
| `string4` | 取气盒管路连接 | cshtml 标签 |
| `string5` | 2 / 系统检查 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `string6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `string7` | 泵头转速是否正常 | cshtml 标签 |
| `string8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `string9` | 泵管卡子松紧度 | cshtml 标签 |
| `remark10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `remark11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `remark12` | 安全瓶 / 无进液 | cshtml 标签 |
| `remark13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `remark14` | 光源LED / 正常光照 | cshtml 标签 |
| `remark15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `remark16` | 红色线是否达到预计值 | cshtml 标签 |
| `remark17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `remark18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `remark19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `remark20` | 测量数据偏离 | cshtml 标签 |
| `remark21` | 是否存在异常数据 | cshtml 标签 |
| `remark22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `remark23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `remark24` | R2避光保护 | cshtml 标签 |
| `remark25` | 外表无破损 | cshtml 标签 |
| `remark26` | 试剂 / 是否过期 | cshtml 标签 |
| `remark27` | 配置是否准确 | cshtml 标签 |
| `remark28` | 剩余量是否充足 | cshtml 标签 |
| `remark29` | 空气过滤膜 / 检查是否需要更换 | cshtml 标签 |
| `remark49` | 异常问题处理记录： | cshtml 标签 |
| `remark50` | 备注： | cshtml 标签 |
| `string10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `string11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `string12` | 安全瓶 / 无进液 | cshtml 标签 |
| `string13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `string14` | 光源LED / 正常光照 | cshtml 标签 |
| `string15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `string16` | 红色线是否达到预计值 | cshtml 标签 |
| `string17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `string18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `string19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `string20` | 测量数据偏离 | cshtml 标签 |
| `string21` | 是否存在异常数据 | cshtml 标签 |
| `string22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `string23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `string24` | R2避光保护 | cshtml 标签 |
| `string25` | 外表无破损 | cshtml 标签 |
| `string26` | 试剂 / 是否过期 | cshtml 标签 |
| `string27` | 配置是否准确 | cshtml 标签 |
| `string28` | 剩余量是否充足 | cshtml 标签 |
| `string29` | 空气过滤膜 / 检查是否需要更换 | cshtml 标签 |
| `string51` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string52` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string53` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string54` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string55` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |

**平台校验器：**`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required


## Sup_RF_HeavyMetalInspection（sup_rf_heavymetalinspection）
- 《组分仪器工单规则》：颗粒物组分/大气重金属仪.docx
- 源码依据：实体 `Sup_RF_HeavyMetalInspection`、视图 `Sup_RF_HeavyMetalInspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `nr1` | （视图标签：1 / 数据采集工控机运行） | 实体注释 |
| `nr2` | （视图标签：2 / 重金属主机运行） | 实体注释 |
| `nr3` | （视图标签：3 / CES-XRF/FP软件运行） | 实体注释 |
| `nr4` | （视图标签：4 / 稳压电压 (V)） | 实体注释 |
| `nr5` | （视图标签：5 / 站房空调运行 (V)） | 实体注释 |
| `nr6` | （视图标签：6 / 采样管法兰防水） | 实体注释 |
| `nr7` | （视图标签：7 / 网络运行） | 实体注释 |
| `nr8` | （视图标签：8 / 设备指示灯显示） | 实体注释 |
| `nr9` | （视图标签：9 / 设备与数采时间校对） | 实体注释 |
| `nrv` | 10 / 稳压电压 (V) | cshtml 标签 |
| `zb1` | （视图标签：1 / 数据采集工控机运行） | 实体注释 |
| `zb2` | （视图标签：2 / 重金属主机运行） | 实体注释 |
| `zb3` | （视图标签：3 / CES-XRF/FP软件运行） | 实体注释 |
| `zb4` | （视图标签：4 / 稳压电压 (V)） | 实体注释 |
| `zb5` | （视图标签：5 / 站房空调运行 (V)） | 实体注释 |
| `zb6` | （视图标签：6 / 采样管法兰防水） | 实体注释 |
| `zb7` | （视图标签：7 / 网络运行） | 实体注释 |
| `zb8` | （视图标签：8 / 设备指示灯显示） | 实体注释 |
| `zb9` | （视图标签：9 / 设备与数采时间校对） | 实体注释 |
| `nr10` | （视图标签：10 / 滤带上滤点圆形） | 实体注释 |
| `nr11` | （视图标签：11 / 流量自动校准结果核查） | 实体注释 |
| `nr12` | （视图标签：12 / UpScale自动校准结果核查） | 实体注释 |
| `nr13` | （视图标签：13 / 清洁颗粒物切割器） | 实体注释 |
| `nr14` | （视图标签：14 / 清洁风扇过滤棉网） | 实体注释 |
| `nr15` | （视图标签：15 / X射线管冷风机运行） | 实体注释 |
| `nr16` | （视图标签：16 / X设备采样流量显示） | 实体注释 |
| `nr17` | （视图标签：17 / X切割器储水罐是否有水） | 实体注释 |
| `nr18` | （视图标签：18 / 滤带是否需要更换） | 实体注释 |
| `nr19` | （视图标签：19 / 仪器是否有报警信息） | 实体注释 |
| `nr20` | （视图标签：20 / 钯元素值是否通过质量核查） | 实体注释 |
| `snsd` | （视图标签：室内温度 / 室内湿度） | 实体注释 |
| `snwd` | （视图标签：室内温度 / 室内湿度） | 实体注释 |
| `zb10` | （视图标签：10 / 滤带上滤点圆形） | 实体注释 |
| `zb11` | （视图标签：11 / 流量自动校准结果核查） | 实体注释 |
| `zb12` | （视图标签：12 / UpScale自动校准结果核查） | 实体注释 |
| `zb13` | （视图标签：13 / 清洁颗粒物切割器） | 实体注释 |
| `zb14` | （视图标签：14 / 清洁风扇过滤棉网） | 实体注释 |
| `zb15` | （视图标签：15 / X射线管冷风机运行） | 实体注释 |
| `zb16` | （视图标签：16 / X设备采样流量显示） | 实体注释 |
| `zb17` | （视图标签：17 / X切割器储水罐是否有水） | 实体注释 |
| `zb18` | （视图标签：18 / 滤带是否需要更换） | 实体注释 |
| `zb19` | （视图标签：19 / 仪器是否有报警信息） | 实体注释 |
| `zb20` | （视图标签：20 / 钯元素值是否通过质量核查） | 实体注释 |

**平台校验器：**`nr16`=required；`nr4`=required；`nrv`=required；`snsd`=required；`snwd`=required；`zb1`=required；`zb10`=required；`zb11`=required；`zb12`=required；`zb13`=required；`zb14`=required；`zb15`=required；`zb16`=required；`zb17`=required；`zb18`=required；`zb19`=required；`zb2`=required；`zb20`=required；`zb3`=required；`zb4`=required；`zb5`=required；`zb6`=required；`zb7`=required；`zb8`=required；`zb9`=required


## Sup_RF_HeavyMetalQuality（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/大气重金属仪.docx
- 源码依据：实体 `Sup_RF_HeavyMetalQuality`、视图 `Sup_RF_HeavyMetalQuality.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |


## Sup_RF_LeakageRateCalibration_i（sup_rf_leakageratecalibration_i）
- 源码依据：实体 `Sup_RF_LeakageRateCalibration_i`、视图 `Sup_RF_LeakageRateCalibration_i.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remarks` | 备注: | cshtml 标签 |
| `humidity` | 室内温/湿度： | cshtml 标签 |
| `leakagerate` | 泄露率 / 是否合格 | cshtml 标签 |
| `qaflow_15_0` | 15.0 L/min | cshtml 标签 |
| `qaflow_16_7` | 16.7 L/min | cshtml 标签 |
| `qaflow_18_4` | 18.4 L/min | cshtml 标签 |
| `temperature` | 室内温/湿度： | cshtml 标签 |
| `analyzermodel` | 上一次 / 下一次 | cshtml 标签 |
| `leakagerateof` | 泄露率 / 是否合格 | cshtml 标签 |
| `analyzernumber` | 上一次 / 下一次 | cshtml 标签 |
| `flowmetermodel` | 截距 / 相关系数 | cshtml 标签 |
| `flowmeterslope` | 截距 / 相关系数 | cshtml 标签 |
| `flowmeternumber` | 截距 / 相关系数 | cshtml 标签 |
| `analyzerlasttime` | 上一次 / 下一次 | cshtml 标签 |
| `displayflow_15_0` | 15.0 L/min | cshtml 标签 |
| `displayflow_16_7` | 16.7 L/min | cshtml 标签 |
| `displayflow_18_4` | 18.4 L/min | cshtml 标签 |
| `qaflowerror_15_0` | 15.0 L/min | cshtml 标签 |
| `qaflowerror_16_7` | 16.7 L/min | cshtml 标签 |
| `qaflowerror_18_4` | 18.4 L/min | cshtml 标签 |
| `flowmeterlasttime` | 截距 / 相关系数 | cshtml 标签 |
| `samplingflow_15_0` | 15.0 L/min | cshtml 标签 |
| `samplingflow_16_7` | 16.7 L/min | cshtml 标签 |
| `samplingflow_18_4` | 18.4 L/min | cshtml 标签 |
| `correctedflow_15_0` | 15.0 L/min | cshtml 标签 |
| `correctedflow_16_7` | 16.7 L/min | cshtml 标签 |
| `correctedflow_18_4` | 18.4 L/min | cshtml 标签 |
| `flowmeterintercept` | 截距 / 相关系数 | cshtml 标签 |
| `analyzeranothertime` | 上一次 / 下一次 | cshtml 标签 |
| `isitcalibrated_15_0` | 15.0 L/min | cshtml 标签 |
| `isitcalibrated_16_7` | 16.7 L/min | cshtml 标签 |
| `isitcalibrated_18_4` | 18.4 L/min | cshtml 标签 |
| `flowmeteranothertime` | 截距 / 相关系数 | cshtml 标签 |
| `flowmetercoefficient` | 截距 / 相关系数 | cshtml 标签 |
| `samplingflowerror_15_0` | 15.0 L/min | cshtml 标签 |
| `samplingflowerror_16_7` | 16.7 L/min | cshtml 标签 |
| `samplingflowerror_18_4` | 18.4 L/min | cshtml 标签 |

**平台校验器：**`analyzermodel`=required；`analyzernumber`=required；`correctedflow_15_0`=required；`correctedflow_16_7`=required；`correctedflow_18_4`=required；`displayflow_15_0`=required；`displayflow_16_7`=required；`displayflow_18_4`=required；`flowmetercoefficient`=required；`flowmeterintercept`=required；`flowmetermodel`=required；`flowmeternumber`=required；`flowmeterslope`=required；`humidity`=required；`leakagerate`=required；`qaflow_15_0`=required；`qaflow_16_7`=required；`qaflow_18_4`=required；`qaflowerror_15_0`=required；`qaflowerror_16_7`=required；`qaflowerror_18_4`=required；`samplingflow_15_0`=required；`samplingflow_16_7`=required；`samplingflow_18_4`=required；`samplingflowerror_15_0`=required；`samplingflowerror_16_7`=required；`samplingflowerror_18_4`=required；`temperature`=required


## Sup_RF_MSFlowCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/单颗粒飞行时间质谱.docx
- 源码依据：实体 `Sup_RF_MSFlowCheck`、视图 `Sup_RF_MSFlowCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | PM2.5在线源解析质谱资料 - 上一次校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time2` | PM2.5在线源解析质谱资料 - 下一次校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time3` | 参考流量计 - 上一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `time4` | 参考流量计 - 下一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `bool_1` | 校准与否（视图标签：校准前） | 实体注释 |
| `string1` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string2` | 出厂编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string3` | 监测项目（视图标签：上一次 / 下一次） | 实体注释 |
| `string4` | 设备/流量计型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string5` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string7` | 截距（视图标签：截距 / 相关系数） | 实体注释 |
| `string8` | 相关系数 | 实体注释 |
| `string9` | 现场温度（视图标签：现场温度 (℃) / 现场大气压 (mmHg)） | 实体注释 |
| `string10` | 现场大气压（视图标签：现场温度 (℃) / 现场大气压 (mmHg)） | 实体注释 |
| `string11` | 设定值 - 校准前 | 实体注释 |
| `string12` | 直接读取的标准读数 - 校准前 | 实体注释 |
| `string13` | 已修正的标准值 - 校准前 | 实体注释 |
| `string14` | 偏差（％）- 校准前 | 实体注释 |
| `string15` | 核查结果 - 校准前 | 实体注释 |
| `string16` | 设定值 - 校准后（视图标签：校准后 / /） | 实体注释 |
| `string17` | 直接读取的标准读数 - 校准后（视图标签：校准后 / /） | 实体注释 |
| `string18` | 已修正的标准值 - 校准后（视图标签：校准后 / /） | 实体注释 |
| `string19` | 偏差（％）- 校准后（视图标签：校准后 / /） | 实体注释 |
| `string20` | 核查结果 - 校准后（视图标签：校准后 / /） | 实体注释 |
| `string27` | 备注： | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required,double；`string12`=required,double；`string13`=required,double；`string14`=required,double；`string15`=required；`string16`=required,double；`string17`=required,double；`string18`=required,double；`string19`=required,double；`string2`=required；`string20`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_MSParticleSizeCalibration（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/单颗粒飞行时间质谱.docx
- 源码依据：实体 `Sup_RF_MSParticleSizeCalibration`、视图 `Sup_RF_MSParticleSizeCalibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 上一次校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time2` | 下一次校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `string1` | 温度（视图标签：温/湿度 / 大气压） | 实体注释 |
| `string2` | 湿度（视图标签：温/湿度 / 大气压） | 实体注释 |
| `string3` | 大气压（视图标签：温/湿度 / 大气压） | 实体注释 |
| `string4` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string5` | 仪器编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string6` | 低真空规三（视图标签：上一次 / 下一次） | 实体注释 |
| `string7` | 粒径 - 1（视图标签：1 / Y=C1+C2*X+C3*X2+C4*X3） | 实体注释 |
| `string8` | 飞行速度记录 - 1（视图标签：1 / Y=C1+C2*X+C3*X2+C4*X3） | 实体注释 |
| `string9` | 粒径校准 - 结果（视图标签：1 / Y=C1+C2*X+C3*X2+C4*X3） | 实体注释 |
| `string10` | 粒径 - 2 | 实体注释 |
| `string11` | 飞行速度记录 - 2 | 实体注释 |
| `string12` | 粒径 - 3 | 实体注释 |
| `string13` | 飞行速度记录 - 3 | 实体注释 |
| `string14` | 粒径 - 4（视图标签：4 / C1= / C2=） | 实体注释 |
| `string15` | 飞行速度记录 - 4（视图标签：4 / C1= / C2=） | 实体注释 |
| `string16` | C1（视图标签：4 / C1= / C2=） | 实体注释 |
| `string17` | C2（视图标签：4 / C1= / C2=） | 实体注释 |
| `string18` | 粒径 - 5（视图标签：5 / C3= / C4=） | 实体注释 |
| `string19` | 飞行速度记录 - 5（视图标签：5 / C3= / C4=） | 实体注释 |
| `string20` | C3（视图标签：5 / C3= / C4=） | 实体注释 |
| `string21` | C4（视图标签：5 / C3= / C4=） | 实体注释 |
| `string22` | 粒径 - 6（视图标签：6 / 相关系数R2=） | 实体注释 |
| `string23` | 飞行速度记录 - 6（视图标签：6 / 相关系数R2=） | 实体注释 |
| `string24` | 相关系数R2（视图标签：6 / 相关系数R2=） | 实体注释 |
| `string25` | 粒径 - 7（视图标签：7 / 参考范围） | 实体注释 |
| `string26` | 飞行速度记录 - 7（视图标签：7 / 参考范围） | 实体注释 |
| `string27` | 参考范围（视图标签：7 / 参考范围） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_MSQualityCalibration（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/单颗粒飞行时间质谱.docx
- 源码依据：实体 `Sup_RF_MSQualityCalibration`、视图 `Sup_RF_MSQualityCalibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | public override bool Bool_1 { get; set; } public override bool Bool_2 { get; set; } public override bool Bool_3 { get; set; } public override bool Bool_4 { get; set; } public override bool Bool_5 { get; set; } public override bool Bool_6 { get; set; } public override bool Bool_7 { get; set; } public override bool Bool_8 { get; set; } public override bool Bool_9 { get; set; } public override bool Bool_10 { get; set; } public override bool Bool_11 { get; set; } public override bool Bool_12 { get; set; } public override bool Bool_13 { get; set; } public override bool Bool_14 { get; set; } public override bool Bool_15 { get; set; } public override bool Bool_16 { get; set; } public override bool Bool_17 { get; set; } public override bool Bool_18 { get; set; } public override bool Bool_19 { get; set; } public override bool Bool_20 { get; set; } public override bool Bool_21 { get; set; } public override bool Bool_22 { get; set; } public override bool Bool_23 { get; set; } public override bool Bool_24 { get; set; } public override bool Bool_25 { get; set; } public override bool Bool_26 { get; set; } public override bool Bool_27 { get; set; } public override bool Bool_28 { get; set; } public override bool Bool_29 { get; set; } public override bool Bool_30 { get; set; } #endregion #region datetime字段 /// <summary> /// 上一次校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time2` | 下一次校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `string1` | 温度（视图标签：温/湿度 / 大气压） | 实体注释 |
| `string2` | 湿度（视图标签：温/湿度 / 大气压） | 实体注释 |
| `string3` | 大气压（视图标签：温/湿度 / 大气压） | 实体注释 |
| `string4` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string5` | 仪器编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string6` | 低真空规三（视图标签：上一次 / 下一次） | 实体注释 |
| `string7` | 最小值amu - 39K+（视图标签：39K+ / 38.5～39.5） | 实体注释 |
| `string8` | 最大值amu - 39K+（视图标签：39K+ / 38.5～39.5） | 实体注释 |
| `string9` | 结果 - 39K+（视图标签：39K+ / 38.5～39.5） | 实体注释 |
| `string10` | 最小值amu - 208Pb+（视图标签：208Pb+ / 207.5～208.5） | 实体注释 |
| `string11` | 最大值amu - 208Pb+（视图标签：208Pb+ / 207.5～208.5） | 实体注释 |
| `string12` | 结果 - 208Pb+（视图标签：208Pb+ / 207.5～208.5） | 实体注释 |
| `string13` | 最小值amu - 46NO2-（视图标签：46NO2- / 45.5～46.5） | 实体注释 |
| `string14` | 最大值amu - 46NO2-（视图标签：46NO2- / 45.5～46.5） | 实体注释 |
| `string15` | 结果 - 46NO2-（视图标签：46NO2- / 45.5～46.5） | 实体注释 |
| `string16` | 最小值amu - 97HSO4-（视图标签：97HSO4- / 96.5～97.5） | 实体注释 |
| `string17` | 最大值amu - 97HSO4-（视图标签：97HSO4- / 96.5～97.5） | 实体注释 |
| `string18` | 结果 - 97HSO4-（视图标签：97HSO4- / 96.5～97.5） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string2`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_MSRoutineCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/单颗粒飞行时间质谱.docx
- 源码依据：实体 `Sup_RF_MSRoutineCheck`、视图 `Sup_RF_MSRoutineCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 仪器状态（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_2` | 分子涡轮泵工作状态（视图标签：2 / 分子涡轮泵工作状态） | 实体注释 |
| `bool_3` | 分子涡轮泵温度（视图标签：3 / 分子涡轮泵温度） | 实体注释 |
| `bool_4` | 真空规状态（视图标签：4 / 真空规状态） | 实体注释 |
| `bool_5` | 低规三（2-2.3toor）（视图标签：5 / 低规三（2-2.3toor）） | 实体注释 |
| `bool_6` | 电离激光冷却水液位（视图标签：6 / 电离激光冷却水液位） | 实体注释 |
| `bool_7` | 电离激光能量值：0.5mJ（视图标签：7 / 电离激光能量值：0.5mJ） | 实体注释 |
| `bool_8` | 采样泵工作状态（视图标签：8 / 采样泵工作状态） | 实体注释 |
| `bool_9` | 变色硅胶使用情况（视图标签：9 / 变色硅胶使用情况） | 实体注释 |
| `bool_10` | 电离图谱情况（视图标签：10 / 电离图谱情况） | 实体注释 |
| `bool_11` | 源解析图谱检查（视图标签：11 / 源解析图谱检查） | 实体注释 |
| `bool_12` | 激光冷却水（视图标签：1 / 激光冷却水） | 实体注释 |
| `bool_13` | 干燥硅胶（视图标签：2 / 干燥硅胶） | 实体注释 |
| `string1` | 仪器状态（视图标签：1 / 仪器状态） | 实体注释 |
| `string2` | 分子涡轮泵工作状态（视图标签：2 / 分子涡轮泵工作状态） | 实体注释 |
| `string3` | 分子涡轮泵工作状态（视图标签：3 / 分子涡轮泵温度） | 实体注释 |
| `string4` | 真空规状态（视图标签：4 / 真空规状态） | 实体注释 |
| `string5` | 低规三（2-2.3toor）（视图标签：5 / 低规三（2-2.3toor）） | 实体注释 |
| `string6` | 电离激光冷却水液位（视图标签：6 / 电离激光冷却水液位） | 实体注释 |
| `string7` | 电离激光能量值：0.5mJ（视图标签：7 / 电离激光能量值：0.5mJ） | 实体注释 |
| `string8` | 采样泵工作状态（视图标签：8 / 采样泵工作状态） | 实体注释 |
| `string9` | 变色硅胶使用情况（视图标签：9 / 变色硅胶使用情况） | 实体注释 |
| `string10` | 电离图谱情况（视图标签：10 / 电离图谱情况） | 实体注释 |
| `string11` | 源解析图谱检查（视图标签：11 / 源解析图谱检查） | 实体注释 |
| `string12` | 激光冷却水（视图标签：1 / 激光冷却水） | 实体注释 |
| `string13` | 干燥硅胶（视图标签：2 / 干燥硅胶） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_MTHNMHCAnalyzer（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/甲烷非甲烷.docx
- 源码依据：实体 `Sup_RF_MTHNMHCAnalyzer`、视图 `Sup_RF_MTHNMHCAnalyzer.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 钢瓶气到期日期 | 实体注释 |
| `bool_1` | 原始数据是否接入数采软件，是否传输至平台 | 实体注释 |
| `bool_2` | 原始数据是否与数采、平台端的数据一样 | 实体注释 |
| `bool_3` | 站点仪器设备等是否整洁（视图标签：站点仪器设备等是否整洁 / 站房排气扇） | 实体注释 |
| `bool_4` | 站房排气扇（视图标签：站点仪器设备等是否整洁 / 站房排气扇） | 实体注释 |
| `bool_5` | 空调设置温度（视图标签：空调设置温度 / ℃ 【25～28】） | 实体注释 |
| `bool_6` | 过滤膜（视图标签：过滤膜 / 仪器排风扇） | 实体注释 |
| `bool_7` | 仪器排风扇（视图标签：过滤膜 / 仪器排风扇） | 实体注释 |
| `bool_8` | 硅胶、分子筛（视图标签：硅胶、分子筛 / 纯水） | 实体注释 |
| `bool_9` | 纯水（视图标签：硅胶、分子筛 / 纯水） | 实体注释 |
| `bool_10` | 仪器管路是否结露 | 实体注释 |
| `bool_11` | 恒温加热 | 实体注释 |
| `bool_12` | 接嘴气密性（视图标签：接嘴气密性 / 采样风机） | 实体注释 |
| `bool_13` | 采样风机（视图标签：接嘴气密性 / 采样风机） | 实体注释 |
| `bool_14` | 校准仪流量认证是否过期 | 实体注释 |
| `bool_15` | 零气发生器（视图标签：校准仪流量认证是否过期） | 实体注释 |
| `bool_16` | 多点校准（视图标签：多点校准 / 零跨校准） | 实体注释 |
| `bool_17` | 零跨校准（视图标签：多点校准 / 零跨校准） | 实体注释 |
| `string1` | 数采情况 处理情况（视图标签：处理情况：） | 实体注释 |
| `string2` | 空调设置温度（视图标签：空调设置温度 / ℃ 【25～28】） | 实体注释 |
| `string3` | 站点环境 处理情况（视图标签：处理情况：） | 实体注释 |
| `string4` | 零氢气一体加热温度（视图标签：仪器管路是否结露） | 实体注释 |
| `string5` | 零气压力（视图标签：仪器管路是否结露 / 正常 异常） | 实体注释 |
| `string6` | 氢气压力（视图标签：正常 异常 / 零气压力 psig【50～60】） | 实体注释 |
| `string7` | 载气压力（视图标签：零气压力 psig【50～60】 / 氢气压力 psig【50～60】） | 实体注释 |
| `string8` | 氢气流量（视图标签：氢气压力 psig【50～60】 / 载气压力 psig【50～60】） | 实体注释 |
| `string9` | 恒温控制温度（视图标签：恒温加热） | 实体注释 |
| `string10` | 采样管 处理情况（视图标签：处理情况：） | 实体注释 |
| `string11` | 钢瓶气 高压 | 实体注释 |
| `string12` | 钢瓶气 低压 | 实体注释 |
| `string13` | 零气发生器（视图标签：校准仪流量认证是否过期） | 实体注释 |
| `string14` | 仪器校准情况 处理情况（视图标签：处理情况：） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string11`=required；`string12`=required；`string13`=required；`string2`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_MaintenanceRecord（sup_rf_maintenancerecord）
- 源码依据：实体 `Sup_RF_MaintenanceRecord`、视图 `Sup_RF_MaintenanceRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `date1` | 甲醛标液 | cshtml 标签 |
| `date2` | 甲醛标液 | cshtml 标签 |
| `date3` | 上次测试日期 / 甲醛摩尔质量(g/mol) / 30.03 | cshtml 标签 |
| `bool_1` | 1 / 霍加拉特剂 / 仅适用雪迪龙 | cshtml 标签 |
| `bool_2` | 2 / 采样总管清洁 / / | cshtml 标签 |
| `bool_3` | 3 / 准确度与精密度测试 / 准确度≤±5% 精密度≤5% | cshtml 标签 |
| `bool_4` | 4 / 检出限 / 检出限≤0.1ppb | cshtml 标签 |
| `remarks` | 备注 | cshtml 标签 |
| `string1` | 1 / 霍加拉特剂 / 仅适用雪迪龙 | cshtml 标签 |
| `string2` | 2 / 采样总管清洁 / / | cshtml 标签 |
| `string3` | 3 / 准确度与精密度测试 / 准确度≤±5% 精密度≤5% | cshtml 标签 |
| `string4` | 4 / 检出限 / 检出限≤0.1ppb | cshtml 标签 |
| `string5` | 甲醛标液 | cshtml 标签 |
| `string6` | 甲醛标液 | cshtml 标签 |
| `string7` | 吸收液流量（ml/min） / 仪器显示采样流量（L/min） | cshtml 标签 |
| `string8` | 吸收液流量（ml/min） / 仪器显示采样流量（L/min） | cshtml 标签 |
| `string9` | 吸收效率 / 气体摩尔体积系数（L/mol） | cshtml 标签 |
| `string10` | 吸收效率 / 气体摩尔体积系数（L/mol） | cshtml 标签 |
| `string11` | 1 | cshtml 标签 |
| `string12` | 1 | cshtml 标签 |
| `string13` | 1 | cshtml 标签 |
| `string14` | 1 | cshtml 标签 |
| `string15` | 1 | cshtml 标签 |
| `string16` | 2 | cshtml 标签 |
| `string17` | 2 | cshtml 标签 |
| `string18` | 2 | cshtml 标签 |
| `string19` | 3 | cshtml 标签 |
| `string20` | 3 | cshtml 标签 |
| `string21` | 3 | cshtml 标签 |
| `string22` | 4 | cshtml 标签 |
| `string23` | 4 | cshtml 标签 |
| `string24` | 4 | cshtml 标签 |
| `string25` | 5 | cshtml 标签 |
| `string26` | 5 | cshtml 标签 |
| `string27` | 5 | cshtml 标签 |
| `string28` | 6 | cshtml 标签 |
| `string29` | 6 | cshtml 标签 |
| `string30` | 6 | cshtml 标签 |
| `string31` | 7 | cshtml 标签 |
| `string32` | 7 | cshtml 标签 |
| `string33` | 7 | cshtml 标签 |
| `string34` | 平均值 / / / / / / | cshtml 标签 |
| `string35` | 平均值 / / / / / / | cshtml 标签 |
| `string36` | 液体甲醛浓度准确度（%） / 气体甲醛浓度准确度（%） | cshtml 标签 |
| `string37` | 液体甲醛浓度准确度（%） / 气体甲醛浓度准确度（%） | cshtml 标签 |
| `string38` | 液体甲醛浓度精密度（%） / 气体甲醛浓度精密度（%） | cshtml 标签 |
| `string39` | 液体甲醛浓度精密度（%） / 气体甲醛浓度精密度（%） | cshtml 标签 |
| `string40` | 1 | cshtml 标签 |
| `string41` | 1 | cshtml 标签 |
| `string42` | 1 | cshtml 标签 |
| `string43` | 1 | cshtml 标签 |
| `string44` | 1 | cshtml 标签 |
| `string45` | 2 | cshtml 标签 |
| `string46` | 2 | cshtml 标签 |
| `string47` | 2 | cshtml 标签 |
| `string48` | 3 | cshtml 标签 |
| `string49` | 3 | cshtml 标签 |
| `string50` | 3 | cshtml 标签 |
| `string51` | 4 | cshtml 标签 |
| `string52` | 4 | cshtml 标签 |
| `string53` | 4 | cshtml 标签 |
| `string54` | 5 | cshtml 标签 |
| `string55` | 5 | cshtml 标签 |
| `string56` | 5 | cshtml 标签 |
| `string57` | 6 | cshtml 标签 |
| `string58` | 6 | cshtml 标签 |
| `string59` | 6 | cshtml 标签 |
| `string60` | 7 | cshtml 标签 |
| `string61` | 7 | cshtml 标签 |
| `string62` | 7 | cshtml 标签 |
| `string63` | 平均值 / / / / / / | cshtml 标签 |
| `string64` | 平均值 / / / / / / | cshtml 标签 |
| `string65` | 液体甲醛浓度MDL（ug/L） / 气体甲醛浓度MDL（ppb） | cshtml 标签 |
| `string66` | 液体甲醛浓度MDL（ug/L） / 气体甲醛浓度MDL（ppb） | cshtml 标签 |

**平台校验器：**`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string46`=required；`string47`=required；`string48`=required；`string49`=required；`string5`=required；`string50`=required；`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required；`string56`=required；`string57`=required；`string58`=required；`string59`=required；`string6`=required；`string60`=required；`string61`=required；`string62`=required；`string63`=required；`string64`=required；`string65`=required；`string66`=required；`string69`=required；`string7`=required；`string70`=required；`string71`=required；`string72`=required；`string73`=required；`string74`=required；`string75`=required；`string76`=required；`string77`=required；`string78`=required；`string79`=required；`string8`=required；`string80`=required；`string81`=required；`string82`=required；`string83`=required；`string84`=required；`string9`=required


## Sup_RF_MonitorInspection_Month（sup_rf_monitorinspection）
- 源码依据：实体 `Sup_RF_MonitorInspection`、视图 `Sup_RF_MonitorInspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `formtype` | 表单类型 周 月 季 | 实体注释 |
| `monthcap` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `monthdate` | 时间日期 / 检查/校准 | cshtml 标签 |
| `monthcutter` | 切割器 / 检查/清洁 | cshtml 标签 |
| `otherremarks` | 其它 | cshtml 标签 |
| `weekaremarks` | 仪器参数 / 检查 | cshtml 标签 |
| `monthcremarks` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `monthdremarks` | 时间日期 / 检查/校准 | cshtml 标签 |
| `weekattribute` | 仪器参数 / 检查 | cshtml 标签 |
| `weekdbremarks` | 除水汽瓶 / 检查 | cshtml 标签 |
| `weekdcremarks` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `weekstremarks` | 稳定性测试 / 检查 | cshtml 标签 |
| `ondemandfilter` | 过滤器 | cshtml 标签 |
| `weekzptremarks` | 零点测试 / 检查 | cshtml 标签 |
| `monthsltremarks` | 样气线管 / 检查/清洁 / 每月 | cshtml 标签 |
| `quarterleaktest` | 检漏测试 / 检查 | cshtml 标签 |
| `quartertrafficv` | 流量验证 / ±5% / 季度 | cshtml 标签 |
| `weekdatacontrol` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `monthcuttremarks` | 切割器 / 检查/清洁 | cshtml 标签 |
| `ondemandfinspect` | 过滤器 | cshtml 标签 |
| `ondemandfremarks` | 过滤器 | cshtml 标签 |
| `ondemandlremarks` | 光腔滑块润滑 / 保养 | cshtml 标签 |
| `quarterltremarks` | 检漏测试 / 检查 | cshtml 标签 |
| `quartertvremarks` | 流量验证 / ±5% / 季度 | cshtml 标签 |
| `ondemandpapertape` | 纸带 | cshtml 标签 |
| `ondemandptinspect` | 纸带 | cshtml 标签 |
| `ondemandptremarks` | 纸带 | cshtml 标签 |
| `ondemandqcremarks` | 光腔 / 检查/清洁 / 按需 | cshtml 标签 |
| `weekdewaterbottle` | 除水汽瓶 / 检查 | cshtml 标签 |
| `weekstabilitytest` | 稳定性测试 / 检查 | cshtml 标签 |
| `weekzeropointtest` | 零点测试 / 检查 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |
| `monthsamplelinetube` | 样气线管 / 检查/清洁 / 每月 | cshtml 标签 |
| `ondemandlubrication` | 光腔滑块润滑 / 保养 | cshtml 标签 |
| `ondemandopticalcavity` | 光腔 / 检查/清洁 / 按需 | cshtml 标签 |


## Sup_RF_MonitorInspection_Quarter（sup_rf_monitorinspection）
- 源码依据：实体 `Sup_RF_MonitorInspection`、视图 `Sup_RF_MonitorInspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `formtype` | 表单类型 周 月 季 | 实体注释 |
| `monthcap` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `monthdate` | 时间日期 / 检查/校准 | cshtml 标签 |
| `monthcutter` | 切割器 / 检查/清洁 | cshtml 标签 |
| `otherremarks` | 其它 | cshtml 标签 |
| `weekaremarks` | 仪器参数 / 检查 | cshtml 标签 |
| `monthcremarks` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `monthdremarks` | 时间日期 / 检查/校准 | cshtml 标签 |
| `weekattribute` | 仪器参数 / 检查 | cshtml 标签 |
| `weekdbremarks` | 除水汽瓶 / 检查 | cshtml 标签 |
| `weekdcremarks` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `weekstremarks` | 稳定性测试 / 检查 | cshtml 标签 |
| `ondemandfilter` | 过滤器 | cshtml 标签 |
| `weekzptremarks` | 零点测试 / 检查 | cshtml 标签 |
| `monthsltremarks` | 样气线管 / 检查/清洁 / 每月 | cshtml 标签 |
| `quarterleaktest` | 检漏测试 / 检查 | cshtml 标签 |
| `quartertrafficv` | 流量验证 / ±5% / 季度 | cshtml 标签 |
| `weekdatacontrol` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `monthcuttremarks` | 切割器 / 检查/清洁 | cshtml 标签 |
| `ondemandfinspect` | 过滤器 | cshtml 标签 |
| `ondemandfremarks` | 过滤器 | cshtml 标签 |
| `ondemandlremarks` | 光腔滑块润滑 / 保养 | cshtml 标签 |
| `quarterltremarks` | 检漏测试 / 检查 | cshtml 标签 |
| `quartertvremarks` | 流量验证 / ±5% / 季度 | cshtml 标签 |
| `ondemandpapertape` | 纸带 | cshtml 标签 |
| `ondemandptinspect` | 纸带 | cshtml 标签 |
| `ondemandptremarks` | 纸带 | cshtml 标签 |
| `ondemandqcremarks` | 光腔 / 检查/清洁 / 按需 | cshtml 标签 |
| `weekdewaterbottle` | 除水汽瓶 / 检查 | cshtml 标签 |
| `weekstabilitytest` | 稳定性测试 / 检查 | cshtml 标签 |
| `weekzeropointtest` | 零点测试 / 检查 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |
| `monthsamplelinetube` | 样气线管 / 检查/清洁 / 每月 | cshtml 标签 |
| `ondemandlubrication` | 光腔滑块润滑 / 保养 | cshtml 标签 |
| `ondemandopticalcavity` | 光腔 / 检查/清洁 / 按需 | cshtml 标签 |


## Sup_RF_MonitorInspection_Week（sup_rf_monitorinspection）
- 源码依据：实体 `Sup_RF_MonitorInspection`、视图 `Sup_RF_MonitorInspection.cshtml`、Vue 移植版 x3

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `formtype` | 表单类型 周 月 季 | 实体注释 |
| `monthcap` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `monthdate` | 时间日期 / 检查/校准 | cshtml 标签 |
| `monthcutter` | 切割器 / 检查/清洁 | cshtml 标签 |
| `otherremarks` | 其它 | cshtml 标签 |
| `weekaremarks` | 仪器参数 / 检查 | cshtml 标签 |
| `monthcremarks` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `monthdremarks` | 时间日期 / 检查/校准 | cshtml 标签 |
| `weekattribute` | 仪器参数 / 检查 | cshtml 标签 |
| `weekdbremarks` | 除水汽瓶 / 检查 | cshtml 标签 |
| `weekdcremarks` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `weekstremarks` | 稳定性测试 / 检查 | cshtml 标签 |
| `ondemandfilter` | 过滤器 | cshtml 标签 |
| `weekzptremarks` | 零点测试 / 检查 | cshtml 标签 |
| `monthsltremarks` | 样气线管 / 检查/清洁 / 每月 | cshtml 标签 |
| `quarterleaktest` | 检漏测试 / 检查 | cshtml 标签 |
| `quartertrafficv` | 流量验证 / ±5% / 季度 | cshtml 标签 |
| `weekdatacontrol` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `monthcuttremarks` | 切割器 / 检查/清洁 | cshtml 标签 |
| `ondemandfinspect` | 过滤器 | cshtml 标签 |
| `ondemandfremarks` | 过滤器 | cshtml 标签 |
| `ondemandlremarks` | 光腔滑块润滑 / 保养 | cshtml 标签 |
| `quarterltremarks` | 检漏测试 / 检查 | cshtml 标签 |
| `quartertvremarks` | 流量验证 / ±5% / 季度 | cshtml 标签 |
| `ondemandpapertape` | 纸带 | cshtml 标签 |
| `ondemandptinspect` | 纸带 | cshtml 标签 |
| `ondemandptremarks` | 纸带 | cshtml 标签 |
| `ondemandqcremarks` | 光腔 / 检查/清洁 / 按需 | cshtml 标签 |
| `weekdewaterbottle` | 除水汽瓶 / 检查 | cshtml 标签 |
| `weekstabilitytest` | 稳定性测试 / 检查 | cshtml 标签 |
| `weekzeropointtest` | 零点测试 / 检查 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |
| `monthsamplelinetube` | 样气线管 / 检查/清洁 / 每月 | cshtml 标签 |
| `ondemandlubrication` | 光腔滑块润滑 / 保养 | cshtml 标签 |
| `ondemandopticalcavity` | 光腔 / 检查/清洁 / 按需 | cshtml 标签 |


## Sup_RF_MonthNepheloMeterCheck（sup_rf_monthnephelometercheck）
- 《组分仪器工单规则》：颗粒物组分/浊度计.docx
- 源码依据：实体 `Sup_RF_MonthNepheloMeterCheck`、视图 `Sup_RF_MonthNepheloMeterCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `yqzt` | （视图标签：1 / 仪器状态 / 若仪器异常需填写故障记录） | 实体注释 |
| `xjbz2` | （视图标签：2 / 仪器运行参数） | 实体注释 |
| `xjbz3` | （视图标签：3 / 仪器运行时钟） | 实体注释 |
| `xjbz4` | （视图标签：4 / 采样风机运转情况） | 实体注释 |
| `yqyxcs` | （视图标签：2 / 仪器运行参数） | 实体注释 |
| `yqyxsz` | （视图标签：3 / 仪器运行时钟） | 实体注释 |
| `clsqsqj` | （视图标签：2 / 测量室腔室清洁） | 实体注释 |
| `hwcytqj` | （视图标签：1 / 户外采样头清洁） | 实体注释 |
| `remark1` | （视图标签：1 / 户外采样头清洁） | 实体注释 |
| `remark2` | （视图标签：2 / 测量室腔室清洁） | 实体注释 |
| `cyfjyzqk` | （视图标签：4 / 采样风机运转情况） | 实体注释 |


## Sup_RF_Month_HONOCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/HONO.docx
- 源码依据：实体 `Sup_RF_Month_HONOCheck`、视图 `Sup_RF_Month_HONOCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：维护单位 / 安装地点 / 维护时间） | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 1 / 室外检查 / 室外取气盒固定是否牢固 | cshtml 标签 |
| `bool_2` | 循环水浴器温控及水位高度 | cshtml 标签 |
| `bool_3` | 取气盒循环水运行检查 | cshtml 标签 |
| `bool_4` | 取气盒管路连接 | cshtml 标签 |
| `bool_5` | 2 / 监测系统 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `bool_6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `bool_7` | 泵头转速是否正常 | cshtml 标签 |
| `bool_8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `bool_9` | 泵管卡子松紧度 | cshtml 标签 |
| `bool_10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `bool_11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `bool_12` | 安全瓶 / 无进液 | cshtml 标签 |
| `bool_13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `bool_14` | 光源LED / 正常光照 | cshtml 标签 |
| `bool_15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `bool_16` | 红色线是否达到预计值 | cshtml 标签 |
| `bool_17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `bool_18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `bool_19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `bool_20` | 测量数据偏离 | cshtml 标签 |
| `bool_21` | 是否存在异常数据 | cshtml 标签 |
| `bool_22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `bool_23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `bool_24` | R2避光保护 | cshtml 标签 |
| `bool_25` | 外表无破损 | cshtml 标签 |
| `bool_26` | 试剂 / 是否过期 | cshtml 标签 |
| `bool_27` | 配置是否准确 | cshtml 标签 |
| `bool_28` | 剩余量是否充足 | cshtml 标签 |
| `remark1` | 1 / 室外检查 / 室外取气盒固定是否牢固 | cshtml 标签 |
| `remark2` | 循环水浴器温控及水位高度 | cshtml 标签 |
| `remark3` | 取气盒循环水运行检查 | cshtml 标签 |
| `remark4` | 取气盒管路连接 | cshtml 标签 |
| `remark5` | 2 / 监测系统 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `remark6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `remark7` | 泵头转速是否正常 | cshtml 标签 |
| `remark8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `remark9` | 泵管卡子松紧度 | cshtml 标签 |
| `string1` | 1 / 室外检查 / 室外取气盒固定是否牢固 | cshtml 标签 |
| `string2` | 循环水浴器温控及水位高度 | cshtml 标签 |
| `string3` | 取气盒循环水运行检查 | cshtml 标签 |
| `string4` | 取气盒管路连接 | cshtml 标签 |
| `string5` | 2 / 监测系统 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `string6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `string7` | 泵头转速是否正常 | cshtml 标签 |
| `string8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `string9` | 泵管卡子松紧度 | cshtml 标签 |
| `remark10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `remark11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `remark12` | 安全瓶 / 无进液 | cshtml 标签 |
| `remark13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `remark14` | 光源LED / 正常光照 | cshtml 标签 |
| `remark15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `remark16` | 红色线是否达到预计值 | cshtml 标签 |
| `remark17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `remark18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `remark19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `remark20` | 测量数据偏离 | cshtml 标签 |
| `remark21` | 是否存在异常数据 | cshtml 标签 |
| `remark22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `remark23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `remark24` | R2避光保护 | cshtml 标签 |
| `remark25` | 外表无破损 | cshtml 标签 |
| `remark26` | 试剂 / 是否过期 | cshtml 标签 |
| `remark27` | 配置是否准确 | cshtml 标签 |
| `remark28` | 剩余量是否充足 | cshtml 标签 |
| `remark49` | 异常问题处理记录： | cshtml 标签 |
| `remark50` | 备注： | cshtml 标签 |
| `string10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `string11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `string12` | 安全瓶 / 无进液 | cshtml 标签 |
| `string13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `string14` | 光源LED / 正常光照 | cshtml 标签 |
| `string15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `string16` | 红色线是否达到预计值 | cshtml 标签 |
| `string17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `string18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `string19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `string20` | 测量数据偏离 | cshtml 标签 |
| `string21` | 是否存在异常数据 | cshtml 标签 |
| `string22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `string23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `string24` | R2避光保护 | cshtml 标签 |
| `string25` | 外表无破损 | cshtml 标签 |
| `string26` | 试剂 / 是否过期 | cshtml 标签 |
| `string27` | 配置是否准确 | cshtml 标签 |
| `string28` | 剩余量是否充足 | cshtml 标签 |
| `string51` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string52` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string53` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string54` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string55` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |

**平台校验器：**`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required


## Sup_RF_Month_HONOTest（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/HONO.docx
- 源码依据：实体 `Sup_RF_Month_HONOTest`、视图 `Sup_RF_Month_HONOTest.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：维护单位 / 安装地点 / 维护时间） | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `string1` | 1 / 零点噪音 / 零气观测稳定后，计算连续25个HONO浓度_分钟值的标准差，均为零点噪音。 | cshtml 标签 |
| `string2` | 1 / 零点噪音 / 零气观测稳定后，计算连续25个HONO浓度_分钟值的标准差，均为零点噪音。 | cshtml 标签 |
| `string3` | 1 / 零点噪音 / 零气观测稳定后，计算连续25个HONO浓度_分钟值的标准差，均为零点噪音。 | cshtml 标签 |
| `string4` | 1 / 零点噪音 / 零气观测稳定后，计算连续25个HONO浓度_分钟值的标准差，均为零点噪音。 | cshtml 标签 |
| `remark50` | 备注： | cshtml 标签 |
| `string51` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string52` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string53` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string54` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string55` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |

**平台校验器：**`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required


## Sup_RF_Month_THLiDAR（sup_rf_common）
- 源码依据：实体 `Sup_RF_Month_THLiDAR`、视图 `Sup_RF_Month_THLiDAR.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 环境检查 / 检查站房周围环境检查站房屋顶是否完好，有无漏雨现象 | cshtml 标签 |
| `bool_2` | 检查站房室内温度、湿度是否符合要求、检查站房空调运行是否正常、检查设备电源插头、稳压电源参数、线板工作是否正常 | cshtml 标签 |
| `bool_3` | 天窗检查及清洁 / 检查天窗玻璃是否破裂，天窗支架及玻璃密封是否完好，有无漏雨现象并清洁天窗玻璃 | cshtml 标签 |
| `bool_4` | 用擦镜布或擦镜纸蘸酒精后将望远镜镜面和天窗灰尘及水渍擦拭干净，镜面表面无灰尘凝结无明显水渍 | cshtml 标签 |
| `bool_5` | 在冬夏季节应注意站房室内外温差，防止天窗出现冷凝水现象，如有此现象需加装加热除湿装置 | cshtml 标签 |
| `bool_6` | 光机镜片清洁 / 用擦镜布或擦镜纸蘸酒精后将光机镜片表面灰尘及水渍擦拭干净，镜片表面无灰尘凝结无明显水渍 | cshtml 标签 |
| `bool_7` | 信号结果检查 / 查看仪器发射、接收系统状况 | cshtml 标签 |
| `bool_8` | 雷达激光能量是否正常 | cshtml 标签 |
| `bool_9` | 激光光斑特征是否正常 | cshtml 标签 |
| `bool_10` | 盲区、过渡区、回波信号、背景基线及噪声是否正常 | cshtml 标签 |
| `bool_11` | 网络项目检查 / 网络连接正常，网速正常 | cshtml 标签 |
| `bool_12` | 雷达布置检查 / 雷达摆放位置平整、支撑稳固、无震动 | cshtml 标签 |
| `remark1` | 环境检查 / 检查站房周围环境检查站房屋顶是否完好，有无漏雨现象 | cshtml 标签 |
| `remark2` | 检查站房室内温度、湿度是否符合要求、检查站房空调运行是否正常、检查设备电源插头、稳压电源参数、线板工作是否正常 | cshtml 标签 |
| `remark3` | 天窗检查及清洁 / 检查天窗玻璃是否破裂，天窗支架及玻璃密封是否完好，有无漏雨现象并清洁天窗玻璃 | cshtml 标签 |
| `remark4` | 用擦镜布或擦镜纸蘸酒精后将望远镜镜面和天窗灰尘及水渍擦拭干净，镜面表面无灰尘凝结无明显水渍 | cshtml 标签 |
| `remark5` | 在冬夏季节应注意站房室内外温差，防止天窗出现冷凝水现象，如有此现象需加装加热除湿装置 | cshtml 标签 |
| `remark6` | 光机镜片清洁 / 用擦镜布或擦镜纸蘸酒精后将光机镜片表面灰尘及水渍擦拭干净，镜片表面无灰尘凝结无明显水渍 | cshtml 标签 |
| `remark7` | 信号结果检查 / 查看仪器发射、接收系统状况 | cshtml 标签 |
| `remark8` | 雷达激光能量是否正常 | cshtml 标签 |
| `remark9` | 激光光斑特征是否正常 | cshtml 标签 |
| `remark10` | 盲区、过渡区、回波信号、背景基线及噪声是否正常 | cshtml 标签 |
| `remark11` | 网络项目检查 / 网络连接正常，网速正常 | cshtml 标签 |
| `remark12` | 雷达布置检查 / 雷达摆放位置平整、支撑稳固、无震动 | cshtml 标签 |


## Sup_RF_Month_YT_FlowCalibration（sup_rf_common）
- 源码依据：实体 `Sup_RF_Month_YT_FlowCalibration`、视图 `Sup_RF_Month_YT_FlowCalibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次校准日期（视图标签：开始时间： / 结束时间：） | 实体注释 |
| `time2` | 参考流量计 - 下一次校准日期（视图标签：开始时间： / 结束时间：） | 实体注释 |
| `time3` | OCEC分析仪资料 - 上一次校准时间（视图标签：流量计证书编号： / 有效期：） | 实体注释 |
| `time4` | OCEC分析仪资料 - 下一次校准时间 | 实体注释 |
| `remark1` | 结论： | cshtml 标签 |
| `string1` | 设备型号（视图标签：记录人：） | 实体注释 |
| `string2` | 出厂编号（视图标签：流量计型号： / 编号：） | 实体注释 |
| `string3` | 斜率（视图标签：流量计型号： / 编号：） | 实体注释 |
| `string4` | 截距（视图标签：流量计证书编号： / 有效期：） | 实体注释 |
| `string5` | 相关系数（视图标签：流量计量程：） | 实体注释 |
| `string6` | 仪器型号（视图标签：1 / 100） | 实体注释 |
| `string7` | 出厂编号（视图标签：1 / 100） | 实体注释 |
| `string8` | 监测项目（视图标签：1 / 100） | 实体注释 |
| `string9` | 设定流量 - 氦气（视图标签：1 / 100） | 实体注释 |
| `string10` | 显示流量 - 氦气（视图标签：2 / 100） | 实体注释 |
| `string11` | 参考流量计读数 - 氦气（视图标签：2 / 100） | 实体注释 |
| `string12` | 参考流量计修正 - 氦气（视图标签：2 / 100） | 实体注释 |
| `string13` | 误差 - 氦气（视图标签：2 / 100） | 实体注释 |
| `string14` | 检查结果 - 氦气（视图标签：3 / 100） | 实体注释 |
| `string15` | 设定流量 - 氦气（吹扫）（视图标签：3 / 100） | 实体注释 |
| `string16` | 显示流量 - 氦气（吹扫）（视图标签：3 / 100） | 实体注释 |
| `string17` | 参考流量计读数 - 氦气（吹扫）（视图标签：3 / 100） | 实体注释 |
| `string18` | 参考流量计修正 - 氦气（吹扫） | 实体注释 |
| `string19` | 误差 - 氦气（吹扫） | 实体注释 |
| `string20` | 检查结果 - 氦气（吹扫） | 实体注释 |
| `string21` | 设定流量 - 氦氧 | 实体注释 |
| `string22` | 显示流量 - 氦氧 | 实体注释 |
| `string23` | 参考流量计读数 - 氦氧 | 实体注释 |
| `string24` | 参考流量计修正 - 氦氧 | 实体注释 |
| `string25` | 误差 - 氦氧 | 实体注释 |
| `string26` | 检查结果 - 氦氧 | 实体注释 |
| `string27` | 设定流量 - 氦甲烷 | 实体注释 |
| `string28` | 显示流量 - 氦甲烷 | 实体注释 |
| `string29` | 参考流量计读数 - 氦甲烷 | 实体注释 |
| `string30` | 参考流量计修正 - 氦甲烷 | 实体注释 |
| `string31` | 误差 - 氦甲烷 | 实体注释 |
| `string32` | 检查结果 - 氦甲烷 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string2`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_Month_YT_LeakChecking（sup_rf_common）
- 源码依据：实体 `Sup_RF_Month_YT_LeakChecking`、视图 `Sup_RF_Month_YT_LeakChecking.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次校准日期（视图标签：开始时间：） | 实体注释 |
| `time2` | 参考流量计 - 下一次校准日期（视图标签：结束时间：） | 实体注释 |
| `time3` | OCEC分析仪资料 - 上一次校准时间 | 实体注释 |
| `time4` | OCEC分析仪资料 - 下一次校准时间 | 实体注释 |
| `string1` | 设备型号（视图标签：记录人：） | 实体注释 |
| `string2` | 出厂编号 | 实体注释 |
| `string3` | 斜率 | 实体注释 |
| `string4` | 截距（视图标签：测量结果（ml/min）） | 实体注释 |
| `string5` | 相关系数（视图标签：测量结果（ml/min）） | 实体注释 |
| `string6` | 仪器型号（视图标签：结论） | 实体注释 |
| `string7` | 出厂编号（视图标签：结论） | 实体注释 |
| `string8` | 监测项目 | 实体注释 |
| `string9` | 设定流量 - 氦气 | 实体注释 |
| `string10` | 显示流量 - 氦气 | 实体注释 |
| `string11` | 参考流量计读数 - 氦气 | 实体注释 |
| `string12` | 参考流量计修正 - 氦气 | 实体注释 |
| `string13` | 误差 - 氦气 | 实体注释 |
| `string14` | 检查结果 - 氦气 | 实体注释 |
| `string15` | 设定流量 - 氦气（吹扫） | 实体注释 |
| `string16` | 显示流量 - 氦气（吹扫） | 实体注释 |
| `string17` | 参考流量计读数 - 氦气（吹扫） | 实体注释 |
| `string18` | 参考流量计修正 - 氦气（吹扫） | 实体注释 |
| `string19` | 误差 - 氦气（吹扫） | 实体注释 |
| `string20` | 检查结果 - 氦气（吹扫） | 实体注释 |
| `string21` | 设定流量 - 氦氧 | 实体注释 |
| `string22` | 显示流量 - 氦氧 | 实体注释 |
| `string23` | 参考流量计读数 - 氦氧 | 实体注释 |
| `string24` | 参考流量计修正 - 氦氧 | 实体注释 |
| `string25` | 误差 - 氦氧 | 实体注释 |
| `string26` | 检查结果 - 氦氧 | 实体注释 |
| `string27` | 设定流量 - 氦甲烷 | 实体注释 |
| `string28` | 显示流量 - 氦甲烷 | 实体注释 |
| `string29` | 参考流量计读数 - 氦甲烷 | 实体注释 |
| `string30` | 参考流量计修正 - 氦甲烷 | 实体注释 |
| `string31` | 误差 - 氦甲烷 | 实体注释 |
| `string32` | 检查结果 - 氦甲烷 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required


## Sup_RF_MultiCalibration（sup_rf_multicalibration）
- 源码依据：实体 `Sup_RF_MultiCalibration`、视图 `Sup_RF_MultiCalibration.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `area1` | 相应面积 - ZERO甲烷（视图标签：分析仪响应 （ppmC） / 相对误差 （%）） | 实体注释 |
| `area2` | 分析仪响应 （ppmC） / 相对误差 （%） | cshtml 标签 |
| `area3` | 满量程的20% | cshtml 标签 |
| `area4` | 满量程的20% | cshtml 标签 |
| `area5` | 满量程的20% / 满量程的40% | cshtml 标签 |
| `area6` | 满量程的40% | cshtml 标签 |
| `area7` | 满量程的40% / 满量程的60% | cshtml 标签 |
| `area8` | 满量程的60% | cshtml 标签 |
| `area9` | 满量程的60% / 满量程的80% | cshtml 标签 |
| `slope` | 斜率（视图标签：斜率 / 截距） | 实体注释 |
| `area10` | 满量程的80% | cshtml 标签 |
| `area11` | 分析仪响应 （ppmC） / 相对误差 （%） | cshtml 标签 |
| `area12` | （视图绑定，含义见标签） | cshtml 标签 |
| `mslope` | 截距（B） / 相关系数（R） | cshtml 标签 |
| `slope1` | 斜率 | 实体注释 |
| `tslope` | 截距（B） / 相关系数（R） | cshtml 标签 |
| `m0error` | 分析仪响应 （ppmC） / 相对误差 （%） | cshtml 标签 |
| `t0error` | 分析仪响应 （ppmC） / 相对误差 （%） | cshtml 标签 |
| `m10error` | （视图绑定，含义见标签） | cshtml 标签 |
| `m20error` | 满量程的20% | cshtml 标签 |
| `m40error` | 满量程的40% | cshtml 标签 |
| `m60error` | 满量程的60% | cshtml 标签 |
| `m80error` | 满量程的80% | cshtml 标签 |
| `pressure` | 更换 / 更换 | cshtml 标签 |
| `residual` | 剩余压力（MPa）【≥2Mpa或300psig】 / 有效与否 | cshtml 标签 |
| `t10error` | （视图绑定，含义见标签） | cshtml 标签 |
| `t20error` | 满量程的20% | cshtml 标签 |
| `t40error` | 满量程的40% | cshtml 标签 |
| `t60error` | 满量程的60% | cshtml 标签 |
| `t80error` | 满量程的80% | cshtml 标签 |
| `thc_type` | 甲烷（最低点0ppm，最高点5ppm） | cshtml 标签 |
| `zermodel` | 出厂编号 / 满量程（ppm） | cshtml 标签 |
| `fullscale` | 满量程 | 实体注释 |
| `intercept` | 截距（视图标签：斜率 / 截距） | 实体注释 |
| `validtill` | 剩余压力（MPa）【≥2Mpa或300psig】 / 有效与否 | cshtml 标签 |
| `zernumber` | 出厂编号 / 满量程（ppm） | cshtml 标签 |
| `intercept1` | 截距 | 实体注释 |
| `m0analyzer` | 分析仪响应 （ppmC） / 相对误差 （%） | cshtml 标签 |
| `mintercept` | 截距（B） / 相关系数（R） | cshtml 标签 |
| `t0analyzer` | 分析仪响应 （ppmC） / 相对误差 （%） | cshtml 标签 |
| `tintercept` | 截距（B） / 相关系数（R） | cshtml 标签 |
| `cylindernum` | 剩余压力（MPa）【≥2Mpa或300psig】 / 有效与否 | cshtml 标签 |
| `instrumentm` | 斜率 / 截距 | cshtml 标签 |
| `m10analyzer` | 相对误差 （%） | cshtml 标签 |
| `m20analyzer` | 满量程的20% | cshtml 标签 |
| `m40analyzer` | 满量程的20% / 满量程的40% | cshtml 标签 |
| `m60analyzer` | 满量程的40% / 满量程的60% | cshtml 标签 |
| `m80analyzer` | 满量程的60% / 满量程的80% | cshtml 标签 |
| `t10analyzer` | （视图绑定，含义见标签） | cshtml 标签 |
| `t20analyzer` | 满量程的20% | cshtml 标签 |
| `t40analyzer` | 满量程的40% | cshtml 标签 |
| `t60analyzer` | 满量程的60% | cshtml 标签 |
| `t80analyzer` | 满量程的80% | cshtml 标签 |
| `dynamictimee` | 斜率 / 截距 | cshtml 标签 |
| `dynamictimes` | 斜率 / 截距 | cshtml 标签 |
| `mcoefficient` | 截距（B） / 相关系数（R） | cshtml 标签 |
| `ptemperature` | 更换 / 更换 | cshtml 标签 |
| `tcoefficient` | 截距（B） / 相关系数（R） | cshtml 标签 |
| `zerfullscale` | 出厂编号 / 满量程（ppm） | cshtml 标签 |
| `m0standardgas` | 分析仪响应 （ppmC） / 相对误差 （%） | cshtml 标签 |
| `purafilvalid1` | 更换 / 更换 | cshtml 标签 |
| `purafilvalid2` | 更换 / 更换 | cshtml 标签 |
| `t0standardgas` | 分析仪响应 （ppmC） / 相对误差 （%） | cshtml 标签 |
| `abnormalremark` | 备注 | cshtml 标签 |
| `m10standardgas` | 相对误差 （%） | cshtml 标签 |
| `m20standardgas` | 满量程的20% | cshtml 标签 |
| `m40standardgas` | 满量程的20% / 满量程的40% | cshtml 标签 |
| `m60standardgas` | 满量程的40% / 满量程的60% | cshtml 标签 |
| `m80standardgas` | 满量程的60% / 满量程的80% | cshtml 标签 |
| `steelisitvalid` | 剩余压力（MPa）【≥2Mpa或300psig】 / 有效与否 | cshtml 标签 |
| `t10standardgas` | （视图绑定，含义见标签） | cshtml 标签 |
| `t20standardgas` | 满量程的20% | cshtml 标签 |
| `t40standardgas` | 满量程的40% | cshtml 标签 |
| `t60standardgas` | 满量程的60% | cshtml 标签 |
| `t80standardgas` | 满量程的80% | cshtml 标签 |
| `temperafactorynum` | 斜率 / 截距 | cshtml 标签 |


## Sup_RF_N2OAnalyzerinspection_HalfYear（sup_rf_n2oanalyzerinspection）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_N2OAnalyzerinspection`、视图 `Sup_RF_N2OAnalyzerinspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `benchpr` | BENCH 温度(℃) / 40-52 | cshtml 标签 |
| `fcdrift` | 流量检查 / 季度 | cshtml 标签 |
| `pcdrift` | 压力检查 | cshtml 标签 |
| `tcdrift` | 温度检查 | cshtml 标签 |
| `ccrvalue` | 最小二乘法校准曲线 / 斜率b ： / 截距a ： / 相关系数 r： | cshtml 标签 |
| `formtype` | 表单类型 周 季 半年 | 实体注释 |
| `zpcdrift` | 零点检查 / 周 | cshtml 标签 |
| `fcendtime` | 流量检查 / 季度 | cshtml 标签 |
| `inttemppr` | 内部温度(℃) / 8.0-47 | cshtml 标签 |
| `pcendtime` | 压力检查 | cshtml 标签 |
| `spandrift` | 跨度检查 | cshtml 标签 |
| `tcendtime` | 温度检查 | cshtml 标签 |
| `fcsetvalue` | 流量检查 / 季度 | cshtml 标签 |
| `pcsetvalue` | 压力检查 | cshtml 标签 |
| `pressurepr` | 压力（mmHg） / 250-1000 | cshtml 标签 |
| `tcsetvalue` | 温度检查 | cshtml 标签 |
| `zpcendtime` | 零点检查 / 周 | cshtml 标签 |
| `automaticpr` | 自动增益强度（Hz） / 150000-300000 | cshtml 标签 |
| `fcstarttime` | 流量检查 / 季度 | cshtml 标签 |
| `pcstarttime` | 压力检查 | cshtml 标签 |
| `slopebvalue` | 最小二乘法校准曲线 / 斜率b ： / 截距a ： / 相关系数 r： | cshtml 标签 |
| `spanendtime` | 跨度检查 | cshtml 标签 |
| `tcstarttime` | 温度检查 | cshtml 标签 |
| `zpcsetvalue` | 零点检查 / 周 | cshtml 标签 |
| `atisitnormal` | 气密性 / 是否正常 / 半年 | cshtml 标签 |
| `ecisitnormal` | 外部清洁 / 是否正常 | cshtml 标签 |
| `fmisitnormal` | 滤膜 / 是否更换 / 按需 | cshtml 标签 |
| `fullscale0az` | 零点 | cshtml 标签 |
| `fullscale0re` | 零点 | cshtml 标签 |
| `fullscale0sg` | 零点 | cshtml 标签 |
| `icisitnormal` | 内部清洁 / 是否正常 | cshtml 标签 |
| `motorspeedpr` | 电机转速 / 100% | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `pmisitnormal` | 泵膜 / 是否更换 | cshtml 标签 |
| `sgisitnormal` | 标气 / 是否更换 | cshtml 标签 |
| `spansetvalue` | 跨度检查 | cshtml 标签 |
| `zpcstarttime` | 零点检查 / 周 | cshtml 标签 |
| `biasvoltagepr` | 偏置电压（V） / -120 - -100 | cshtml 标签 |
| `fullscale10az` | 满量程的 10% | cshtml 标签 |
| `fullscale10re` | 满量程的 10% | cshtml 标签 |
| `fullscale10sg` | 满量程的 10% | cshtml 标签 |
| `fullscale30az` | 满量程的 30% | cshtml 标签 |
| `fullscale30re` | 满量程的 30% | cshtml 标签 |
| `fullscale30sg` | 满量程的 30% | cshtml 标签 |
| `fullscale50az` | 满量程的 50% | cshtml 标签 |
| `fullscale50re` | 满量程的 50% | cshtml 标签 |
| `fullscale50sg` | 满量程的 50% | cshtml 标签 |
| `fullscale70az` | 满量程的 70% | cshtml 标签 |
| `fullscale70re` | 满量程的 70% | cshtml 标签 |
| `fullscale70sg` | 满量程的 70% | cshtml 标签 |
| `fullscale90az` | 满量程的 90% | cshtml 标签 |
| `fullscale90re` | 满量程的 90% | cshtml 标签 |
| `fullscale90sg` | 满量程的 90% | cshtml 标签 |
| `gpcisitnormal` | 气路清洁 / 是否正常 | cshtml 标签 |
| `spanstarttime` | 跨度检查 | cshtml 标签 |
| `fcdisplayvalue` | 流量检查 / 季度 | cshtml 标签 |
| `pcdisplayvalue` | 压力检查 | cshtml 标签 |
| `samplingflowpr` | 采样流量（L/min） / 0.350-1.500 | cshtml 标签 |
| `tcdisplayvalue` | 温度检查 | cshtml 标签 |
| `automaticcvalue` | 自动增益强度（Hz） / 150000-300000 | cshtml 标签 |
| `benchcheckvalue` | BENCH 温度(℃) / 40-52 | cshtml 标签 |
| `fullscale0etime` | 零点 | cshtml 标签 |
| `fullscale0stime` | 零点 | cshtml 标签 |
| `interceptavalue` | 最小二乘法校准曲线 / 斜率b ： / 截距a ： / 相关系数 r： | cshtml 标签 |
| `zpcdisplayvalue` | 零点检查 / 周 | cshtml 标签 |
| `fcisitcalibrated` | 流量检查 / 季度 | cshtml 标签 |
| `fullscale10etime` | 满量程的 10% | cshtml 标签 |
| `fullscale10stime` | 满量程的 10% | cshtml 标签 |
| `fullscale30etime` | 满量程的 30% | cshtml 标签 |
| `fullscale30stime` | 满量程的 30% | cshtml 标签 |
| `fullscale50etime` | 满量程的 50% | cshtml 标签 |
| `fullscale50stime` | 满量程的 50% | cshtml 标签 |
| `fullscale70etime` | 满量程的 70% | cshtml 标签 |
| `fullscale70stime` | 满量程的 70% | cshtml 标签 |
| `fullscale90etime` | 满量程的 90% | cshtml 标签 |
| `fullscale90stime` | 满量程的 90% | cshtml 标签 |
| `motorspeedcvalue` | 电机转速 / 100% | cshtml 标签 |
| `pcisitcalibrated` | 压力检查 | cshtml 标签 |
| `spandisplayvalue` | 跨度检查 | cshtml 标签 |
| `tcisitcalibrated` | 温度检查 | cshtml 标签 |
| `biasvoltagecvalue` | 偏置电压（V） / -120 - -100 | cshtml 标签 |
| `inttempcheckvalue` | 内部温度(℃) / 8.0-47 | cshtml 标签 |
| `zpcisitcalibrated` | 零点检查 / 周 | cshtml 标签 |
| `pressurecheckvalue` | 压力（mmHg） / 250-1000 | cshtml 标签 |
| `samplingflowcvalue` | 采样流量（L/min） / 0.350-1.500 | cshtml 标签 |
| `spanisitcalibrated` | 跨度检查 | cshtml 标签 |


## Sup_RF_N2OAnalyzerinspection_Week（sup_rf_n2oanalyzerinspection）
- 《组分仪器工单规则》：温室气体/（中精度CO2+高精度温室气体）.docx
- 源码依据：实体 `Sup_RF_N2OAnalyzerinspection`、视图 `Sup_RF_N2OAnalyzerinspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `benchpr` | BENCH 温度(℃) / 40-52 | cshtml 标签 |
| `fcdrift` | 流量检查 / 季度 | cshtml 标签 |
| `pcdrift` | 压力检查 | cshtml 标签 |
| `tcdrift` | 温度检查 | cshtml 标签 |
| `ccrvalue` | 最小二乘法校准曲线 / 斜率b ： / 截距a ： / 相关系数 r： | cshtml 标签 |
| `formtype` | 表单类型 周 季 半年 | 实体注释 |
| `zpcdrift` | 零点检查 / 周 | cshtml 标签 |
| `fcendtime` | 流量检查 / 季度 | cshtml 标签 |
| `inttemppr` | 内部温度(℃) / 8.0-47 | cshtml 标签 |
| `pcendtime` | 压力检查 | cshtml 标签 |
| `spandrift` | 跨度检查 | cshtml 标签 |
| `tcendtime` | 温度检查 | cshtml 标签 |
| `fcsetvalue` | 流量检查 / 季度 | cshtml 标签 |
| `pcsetvalue` | 压力检查 | cshtml 标签 |
| `pressurepr` | 压力（mmHg） / 250-1000 | cshtml 标签 |
| `tcsetvalue` | 温度检查 | cshtml 标签 |
| `zpcendtime` | 零点检查 / 周 | cshtml 标签 |
| `automaticpr` | 自动增益强度（Hz） / 150000-300000 | cshtml 标签 |
| `fcstarttime` | 流量检查 / 季度 | cshtml 标签 |
| `pcstarttime` | 压力检查 | cshtml 标签 |
| `slopebvalue` | 最小二乘法校准曲线 / 斜率b ： / 截距a ： / 相关系数 r： | cshtml 标签 |
| `spanendtime` | 跨度检查 | cshtml 标签 |
| `tcstarttime` | 温度检查 | cshtml 标签 |
| `zpcsetvalue` | 零点检查 / 周 | cshtml 标签 |
| `atisitnormal` | 气密性 / 是否正常 / 半年 | cshtml 标签 |
| `ecisitnormal` | 外部清洁 / 是否正常 | cshtml 标签 |
| `fmisitnormal` | 滤膜 / 是否更换 / 按需 | cshtml 标签 |
| `fullscale0az` | 零点 | cshtml 标签 |
| `fullscale0re` | 零点 | cshtml 标签 |
| `fullscale0sg` | 零点 | cshtml 标签 |
| `icisitnormal` | 内部清洁 / 是否正常 | cshtml 标签 |
| `motorspeedpr` | 电机转速 / 100% | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `pmisitnormal` | 泵膜 / 是否更换 | cshtml 标签 |
| `sgisitnormal` | 标气 / 是否更换 | cshtml 标签 |
| `spansetvalue` | 跨度检查 | cshtml 标签 |
| `zpcstarttime` | 零点检查 / 周 | cshtml 标签 |
| `biasvoltagepr` | 偏置电压（V） / -120 - -100 | cshtml 标签 |
| `fullscale10az` | 满量程的 10% | cshtml 标签 |
| `fullscale10re` | 满量程的 10% | cshtml 标签 |
| `fullscale10sg` | 满量程的 10% | cshtml 标签 |
| `fullscale30az` | 满量程的 30% | cshtml 标签 |
| `fullscale30re` | 满量程的 30% | cshtml 标签 |
| `fullscale30sg` | 满量程的 30% | cshtml 标签 |
| `fullscale50az` | 满量程的 50% | cshtml 标签 |
| `fullscale50re` | 满量程的 50% | cshtml 标签 |
| `fullscale50sg` | 满量程的 50% | cshtml 标签 |
| `fullscale70az` | 满量程的 70% | cshtml 标签 |
| `fullscale70re` | 满量程的 70% | cshtml 标签 |
| `fullscale70sg` | 满量程的 70% | cshtml 标签 |
| `fullscale90az` | 满量程的 90% | cshtml 标签 |
| `fullscale90re` | 满量程的 90% | cshtml 标签 |
| `fullscale90sg` | 满量程的 90% | cshtml 标签 |
| `gpcisitnormal` | 气路清洁 / 是否正常 | cshtml 标签 |
| `spanstarttime` | 跨度检查 | cshtml 标签 |
| `fcdisplayvalue` | 流量检查 / 季度 | cshtml 标签 |
| `pcdisplayvalue` | 压力检查 | cshtml 标签 |
| `samplingflowpr` | 采样流量（L/min） / 0.350-1.500 | cshtml 标签 |
| `tcdisplayvalue` | 温度检查 | cshtml 标签 |
| `automaticcvalue` | 自动增益强度（Hz） / 150000-300000 | cshtml 标签 |
| `benchcheckvalue` | BENCH 温度(℃) / 40-52 | cshtml 标签 |
| `fullscale0etime` | 零点 | cshtml 标签 |
| `fullscale0stime` | 零点 | cshtml 标签 |
| `interceptavalue` | 最小二乘法校准曲线 / 斜率b ： / 截距a ： / 相关系数 r： | cshtml 标签 |
| `zpcdisplayvalue` | 零点检查 / 周 | cshtml 标签 |
| `fcisitcalibrated` | 流量检查 / 季度 | cshtml 标签 |
| `fullscale10etime` | 满量程的 10% | cshtml 标签 |
| `fullscale10stime` | 满量程的 10% | cshtml 标签 |
| `fullscale30etime` | 满量程的 30% | cshtml 标签 |
| `fullscale30stime` | 满量程的 30% | cshtml 标签 |
| `fullscale50etime` | 满量程的 50% | cshtml 标签 |
| `fullscale50stime` | 满量程的 50% | cshtml 标签 |
| `fullscale70etime` | 满量程的 70% | cshtml 标签 |
| `fullscale70stime` | 满量程的 70% | cshtml 标签 |
| `fullscale90etime` | 满量程的 90% | cshtml 标签 |
| `fullscale90stime` | 满量程的 90% | cshtml 标签 |
| `motorspeedcvalue` | 电机转速 / 100% | cshtml 标签 |
| `pcisitcalibrated` | 压力检查 | cshtml 标签 |
| `spandisplayvalue` | 跨度检查 | cshtml 标签 |
| `tcisitcalibrated` | 温度检查 | cshtml 标签 |
| `biasvoltagecvalue` | 偏置电压（V） / -120 - -100 | cshtml 标签 |
| `inttempcheckvalue` | 内部温度(℃) / 8.0-47 | cshtml 标签 |
| `zpcisitcalibrated` | 零点检查 / 周 | cshtml 标签 |
| `pressurecheckvalue` | 压力（mmHg） / 250-1000 | cshtml 标签 |
| `samplingflowcvalue` | 采样流量（L/min） / 0.350-1.500 | cshtml 标签 |
| `spanisitcalibrated` | 跨度检查 | cshtml 标签 |


## Sup_RF_NH3AnalyzerInspection_HalfYear（sup_rf_nh3analyzerinspection）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3AnalyzerInspection`、视图 `Sup_RF_NH3AnalyzerInspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `slopeb` | 最小二乘法校准曲线 / 斜率b / 截距a / 相关系数r | cshtml 标签 |
| `fcdrift` | 流量检查 / 季度 | cshtml 标签 |
| `pcdrift` | 压力检查 | cshtml 标签 |
| `scdrift` | 跨度检查 | cshtml 标签 |
| `tcdrift` | 温度检查 | cshtml 标签 |
| `fcdvalue` | 流量检查 / 季度 | cshtml 标签 |
| `formtype` | 表单类型 周 季 半年 | 实体注释 |
| `scdvalue` | 跨度检查 | cshtml 标签 |
| `zpcdrift` | 零点检查 / 周 | cshtml 标签 |
| `fcendtime` | 流量检查 / 季度 | cshtml 标签 |
| `fs20etime` | 满量程的 20% | cshtml 标签 |
| `fs20stime` | 满量程的 20% | cshtml 标签 |
| `fs30etime` | 满量程的 30% | cshtml 标签 |
| `fs30stime` | 满量程的 30% | cshtml 标签 |
| `fs40etime` | 满量程的 40% | cshtml 标签 |
| `fs40stime` | 满量程的 40% | cshtml 标签 |
| `fs50etime` | 满量程的 50% | cshtml 标签 |
| `fs50stime` | 满量程的 50% | cshtml 标签 |
| `fs60etime` | 满量程的 60% | cshtml 标签 |
| `fs60stime` | 满量程的 60% | cshtml 标签 |
| `fs70etime` | 满量程的 70% | cshtml 标签 |
| `fs70stime` | 满量程的 70% | cshtml 标签 |
| `fs80etime` | 满量程的 80% | cshtml 标签 |
| `fs80stime` | 满量程的 80% | cshtml 标签 |
| `pcendtime` | 压力检查 | cshtml 标签 |
| `scendtime` | 跨度检查 | cshtml 标签 |
| `tcendtime` | 温度检查 | cshtml 标签 |
| `zpcdvalue` | 零点检查 / 周 | cshtml 标签 |
| `fcsetvalue` | 流量检查 / 季度 | cshtml 标签 |
| `intercepta` | 最小二乘法校准曲线 / 斜率b / 截距a / 相关系数r | cshtml 标签 |
| `pcsetvalue` | 压力检查 | cshtml 标签 |
| `scsetvalue` | 跨度检查 | cshtml 标签 |
| `tcsetvalue` | 温度检查 | cshtml 标签 |
| `zpcendtime` | 零点检查 / 周 | cshtml 标签 |
| `ctabnormalr` | 毛细管温度(℃) / 48-52 | cshtml 标签 |
| `fcstarttime` | 流量检查 / 季度 | cshtml 标签 |
| `fs20arvalue` | 满量程的 20% | cshtml 标签 |
| `fs20revalue` | 满量程的 20% | cshtml 标签 |
| `fs30arvalue` | 满量程的 30% | cshtml 标签 |
| `fs30revalue` | 满量程的 30% | cshtml 标签 |
| `fs40arvalue` | 满量程的 40% | cshtml 标签 |
| `fs40revalue` | 满量程的 40% | cshtml 标签 |
| `fs50arvalue` | 满量程的 50% | cshtml 标签 |
| `fs50revalue` | 满量程的 50% | cshtml 标签 |
| `fs60arvalue` | 满量程的 60% | cshtml 标签 |
| `fs60revalue` | 满量程的 60% | cshtml 标签 |
| `fs70arvalue` | 满量程的 70% | cshtml 标签 |
| `fs70revalue` | 满量程的 70% | cshtml 标签 |
| `fs80arvalue` | 满量程的 80% | cshtml 标签 |
| `fs80revalue` | 满量程的 80% | cshtml 标签 |
| `itabnormalr` | 内部温度(℃) / 15-45 | cshtml 标签 |
| `pcstarttime` | 压力检查 | cshtml 标签 |
| `scstarttime` | 跨度检查 | cshtml 标签 |
| `tcstarttime` | 温度检查 | cshtml 标签 |
| `zpcsetvalue` | 零点检查 / 周 | cshtml 标签 |
| `atisitnormal` | 气密性 / 是否正常 / 半年 | cshtml 标签 |
| `coefficientr` | 最小二乘法校准曲线 / 斜率b / 截距a / 相关系数r | cshtml 标签 |
| `ctcheckvalue` | 毛细管温度(℃) / 48-52 | cshtml 标签 |
| `ecisitnormal` | 外部清洁 / 是否正常 | cshtml 标签 |
| `ectabnormalr` | 外部转换器温度(℃) / 725-775 | cshtml 标签 |
| `fs20sgcvalue` | 满量程的 20% | cshtml 标签 |
| `fs30sgcvalue` | 满量程的 30% | cshtml 标签 |
| `fs40sgcvalue` | 满量程的 40% | cshtml 标签 |
| `fs50sgcvalue` | 满量程的 50% | cshtml 标签 |
| `fs60sgcvalue` | 满量程的 60% | cshtml 标签 |
| `fs70sgcvalue` | 满量程的 70% | cshtml 标签 |
| `fs80sgcvalue` | 满量程的 80% | cshtml 标签 |
| `icisitnormal` | 内部清洁 / 是否正常 | cshtml 标签 |
| `itcheckvalue` | 内部温度(℃) / 15-45 | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `rcpabnormalr` | 反应室压力（mmHg） / 50-150 | cshtml 标签 |
| `trcabnormalr` | 反应室温度(℃) / 48-52 | cshtml 标签 |
| `zpcstarttime` | 零点检查 / 周 | cshtml 标签 |
| `contabnormalr` | 转换炉温度(℃) / 300-350 | cshtml 标签 |
| `cootabnormalr` | 制冷器温度(℃) / （-12） - (-1.0) | cshtml 标签 |
| `ectcheckvalue` | 外部转换器温度(℃) / 725-775 | cshtml 标签 |
| `flowabnormalr` | 流量（L/min） / 0.350-0.900 | cshtml 标签 |
| `gpcisitnormal` | 气路清洁 / 是否正常 | cshtml 标签 |
| `rcpcheckvalue` | 反应室压力（mmHg） / 50-150 | cshtml 标签 |
| `trccheckvalue` | 反应室温度(℃) / 48-52 | cshtml 标签 |
| `contcheckvalue` | 转换炉温度(℃) / 300-350 | cshtml 标签 |
| `cootcheckvalue` | 制冷器温度(℃) / （-12） - (-1.0) | cshtml 标签 |
| `flowcheckvalue` | 流量（L/min） / 0.350-0.900 | cshtml 标签 |
| `fmisitreplaced` | 滤膜 / 是否更换 / 按需 | cshtml 标签 |
| `oflowabnormalr` | 臭氧流量（L/min） / ＞0.050 | cshtml 标签 |
| `pcdisplayvalue` | 压力检查 | cshtml 标签 |
| `pmisitreplaced` | 泵膜 / 是否更换 | cshtml 标签 |
| `sgisitreplaced` | 标气 / 是否更换 | cshtml 标签 |
| `tcdisplayvalue` | 温度检查 | cshtml 标签 |
| `csgisitreplaced` | 变色硅胶 / 是否更换 | cshtml 标签 |
| `oflowcheckvalue` | 臭氧流量（L/min） / ＞0.050 | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `fcisitcalibrated` | 流量检查 / 季度 | cshtml 标签 |
| `pcisitcalibrated` | 压力检查 | cshtml 标签 |
| `scisitcalibrated` | 跨度检查 | cshtml 标签 |
| `tcisitcalibrated` | 温度检查 | cshtml 标签 |
| `zpcisitcalibrated` | 零点检查 / 周 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |


## Sup_RF_NH3Calibration（sup_rf_nh3calibration）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3Calibration`、视图 `Sup_RF_NH3Calibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `int1` | 采样管检查（附件上传检查照片） | cshtml 标签 |
| `remark1` | 采样流量 (试样流量/样气流量/总量) / 0.35-0.9LPM | cshtml 标签 |
| `remark2` | 臭氧流量 (氧量) / ＞0.05LPM | cshtml 标签 |
| `remark3` | 参考PMT信号 (光电倍增管测量信号/模拟电压) | cshtml 标签 |
| `remark4` | 高压电源 (光电倍增管高压) | cshtml 标签 |
| `remark5` | PMT电压 / ＞0（赛默飞设备以仪器界面数值为准） | cshtml 标签 |
| `remark6` | 反应室温度 (测量室温度/试样槽温度) / 300-350℃ | cshtml 标签 |
| `remark7` | 转化炉温度 (转换炉) / 725-800℃ | cshtml 标签 |
| `remark8` | 反应室压力 (测量室内部的真空压) / 50-150mmhg | cshtml 标签 |
| `remark9` | 采样压力 (样气压力/试样压力) | cshtml 标签 |
| `string1` | 采样流量 (试样流量/样气流量/总量) / 0.35-0.9LPM | cshtml 标签 |
| `string2` | 臭氧流量 (氧量) / ＞0.05LPM | cshtml 标签 |
| `string3` | 参考PMT信号 (光电倍增管测量信号/模拟电压) | cshtml 标签 |
| `string4` | 高压电源 (光电倍增管高压) | cshtml 标签 |
| `string5` | PMT电压 / ＞0（赛默飞设备以仪器界面数值为准） | cshtml 标签 |
| `string6` | 反应室温度 (测量室温度/试样槽温度) / 300-350℃ | cshtml 标签 |
| `string7` | 转化炉温度 (转换炉) / 725-800℃ | cshtml 标签 |
| `string8` | 反应室压力 (测量室内部的真空压) / 50-150mmhg | cshtml 标签 |
| `string9` | 采样压力 (样气压力/试样压力) | cshtml 标签 |
| `string10` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `string11` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `string12` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `string13` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `string14` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `string15` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `string16` | 零点 | cshtml 标签 |
| `string17` | 零点 | cshtml 标签 |
| `string18` | 零点 | cshtml 标签 |
| `string19` | 零点漂移 | cshtml 标签 |
| `string20` | 80%满量程 | cshtml 标签 |
| `string21` | 80%满量程 | cshtml 标签 |
| `string22` | 80%满量程 | cshtml 标签 |
| `string23` | 跨度漂移(%) | cshtml 标签 |
| `string24` | 工作点 | cshtml 标签 |
| `string25` | 工作点 | cshtml 标签 |
| `string26` | 工作点 | cshtml 标签 |
| `string27` | 工作点正确度(%) | cshtml 标签 |
| `datetime1` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `datetime2` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `datetime3` | 起始时间 / 结束时间 | cshtml 标签 |
| `datetime4` | 起始时间 / 结束时间 | cshtml 标签 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_NH3CalibrationCX（sup_rf_nh3calibration）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3Calibration`、视图 `Sup_RF_NH3Calibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `int1` | 采样管检查（附件上传检查照片） | cshtml 标签 |
| `remark1` | 采样流量 (试样流量/样气流量/总量) / 0.35-0.9LPM | cshtml 标签 |
| `remark2` | 臭氧流量 (氧量) / ＞0.05LPM | cshtml 标签 |
| `remark3` | 参考PMT信号 (光电倍增管测量信号/模拟电压) | cshtml 标签 |
| `remark4` | 高压电源 (光电倍增管高压) | cshtml 标签 |
| `remark5` | PMT电压 / ＞0（赛默飞设备以仪器界面数值为准） | cshtml 标签 |
| `remark6` | 反应室温度 (测量室温度/试样槽温度) / 300-350℃ | cshtml 标签 |
| `remark7` | 转化炉温度 (转换炉) / 725-800℃ | cshtml 标签 |
| `remark8` | 反应室压力 (测量室内部的真空压) / 50-150mmhg | cshtml 标签 |
| `remark9` | 采样压力 (样气压力/试样压力) | cshtml 标签 |
| `string1` | 采样流量 (试样流量/样气流量/总量) / 0.35-0.9LPM | cshtml 标签 |
| `string2` | 臭氧流量 (氧量) / ＞0.05LPM | cshtml 标签 |
| `string3` | 参考PMT信号 (光电倍增管测量信号/模拟电压) | cshtml 标签 |
| `string4` | 高压电源 (光电倍增管高压) | cshtml 标签 |
| `string5` | PMT电压 / ＞0（赛默飞设备以仪器界面数值为准） | cshtml 标签 |
| `string6` | 反应室温度 (测量室温度/试样槽温度) / 300-350℃ | cshtml 标签 |
| `string7` | 转化炉温度 (转换炉) / 725-800℃ | cshtml 标签 |
| `string8` | 反应室压力 (测量室内部的真空压) / 50-150mmhg | cshtml 标签 |
| `string9` | 采样压力 (样气压力/试样压力) | cshtml 标签 |
| `string10` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `string11` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `string12` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `string13` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `string14` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `string15` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `string16` | 零点 | cshtml 标签 |
| `string17` | 零点 | cshtml 标签 |
| `string18` | 零点 | cshtml 标签 |
| `string19` | 零点漂移 | cshtml 标签 |
| `string20` | 80%满量程 | cshtml 标签 |
| `string21` | 80%满量程 | cshtml 标签 |
| `string22` | 80%满量程 | cshtml 标签 |
| `string23` | 跨度漂移(%) | cshtml 标签 |
| `string24` | 工作点 | cshtml 标签 |
| `string25` | 工作点 | cshtml 标签 |
| `string26` | 工作点 | cshtml 标签 |
| `string27` | 工作点正确度(%) | cshtml 标签 |
| `datetime1` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `datetime2` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `datetime3` | 起始时间 / 结束时间 | cshtml 标签 |
| `datetime4` | 起始时间 / 结束时间 | cshtml 标签 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_NH3ConversionRate（sup_rf_nh3conversionrate）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3ConversionRate`、视图 `Sup_RF_NH3ConversionRate.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bjzh` | NO 2 平均转化效率 | cshtml 标签 |
| `zhxl1` | NO 2 转化效率 | cshtml 标签 |
| `zhxl2` | NO 2 转化效率 | cshtml 标签 |
| `zhxl3` | NO 2 转化效率 | cshtml 标签 |
| `remrow11` | 开 / [NO]rem | cshtml 标签 |
| `remrow12` | 开 / [NO]rem | cshtml 标签 |
| `remrow13` | 开 / [NO]rem | cshtml 标签 |
| `remrow21` | [NOx]rem | cshtml 标签 |
| `remrow22` | [NOx]rem | cshtml 标签 |
| `remrow23` | [NOx]rem | cshtml 标签 |
| `sczhxl20` | 20%（40ppb） | cshtml 标签 |
| `sczhxl40` | 40%（80ppb） | cshtml 标签 |
| `sczhxl80` | 80%（160ppb） | cshtml 标签 |
| `yqxsnd20` | 20%（40ppb） | cshtml 标签 |
| `yqxsnd40` | 40%（80ppb） | cshtml 标签 |
| `yqxsnd80` | 80%（160ppb） | cshtml 标签 |
| `nh3zhxl20` | 20%（40ppb） | cshtml 标签 |
| `nh3zhxl40` | 40%（80ppb） | cshtml 标签 |
| `nh3zhxl80` | 80%（160ppb） | cshtml 标签 |
| `origrow11` | NO满量程80% O 3 满量程40% / 关 / [NO]orig | cshtml 标签 |
| `origrow12` | NO满量程80% O 3 满量程40% / 关 / [NO]orig | cshtml 标签 |
| `origrow13` | NO满量程80% O 3 满量程40% / 关 / [NO]orig | cshtml 标签 |
| `origrow21` | [NOx]orig | cshtml 标签 |
| `origrow22` | [NOx]orig | cshtml 标签 |
| `origrow23` | [NOx]orig | cshtml 标签 |
| `bzqtllnd20` | 20%（40ppb） | cshtml 标签 |
| `bzqtllnd40` | 40%（80ppb） | cshtml 标签 |
| `bzqtllnd80` | 80%（160ppb） | cshtml 标签 |
| `ysczhxlpc20` | 20%（40ppb） | cshtml 标签 |
| `ysczhxlpc40` | 40%（80ppb） | cshtml 标签 |
| `ysczhxlpc80` | 80%（160ppb） | cshtml 标签 |


## Sup_RF_NH3DeviceMultipoint（sup_rf_nh3devicemultipoint）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3DeviceMultipoint`、视图 `Sup_RF_NH3DeviceMultipoint.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `ju` | 截距a（视图标签：校准曲线 / （Y=aX+b）） | 实体注释 |
| `xl` | 斜率b（视图标签：校准曲线 / （Y=aX+b）） | 实体注释 |
| `ppb` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `xgxs` | 相关系数r（视图标签：校准曲线 / （Y=aX+b）） | 实体注释 |
| `xzjg` | 校准结果 //（合格/不合格） | 实体注释 |
| `gasmic` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `endtime` | 起始时间 / 结束时间 | cshtml 标签 |
| `mclbz10` | 满程量10标准值（视图标签：满量程的10％） | 实体注释 |
| `mclbz20` | 满程量20标准值（视图标签：满量程的20％） | 实体注释 |
| `mclbz40` | 满程量40标准值（视图标签：满量程的40％） | 实体注释 |
| `mclbz60` | 满程量60标准值（视图标签：满量程的60％） | 实体注释 |
| `mclbz80` | 满程量80标准值（视图标签：满量程的80％） | 实体注释 |
| `mclxy10` | 满程量10响应值（视图标签：满量程的10％） | 实体注释 |
| `mclxy20` | 满程量20响应值（视图标签：满量程的20％） | 实体注释 |
| `mclxy40` | 满程量40响应值（视图标签：满量程的40％） | 实体注释 |
| `mclxy60` | 满程量60响应值（视图标签：满量程的60％） | 实体注释 |
| `mclxy80` | 满程量80响应值（视图标签：满量程的80％） | 实体注释 |
| `remark1` | 备注： | cshtml 标签 |
| `mclby101` | 满程量10备用记录1（视图标签：满量程的10％） | 实体注释 |
| `mclby102` | 满程量10备用记录2（视图标签：满量程的10％） | 实体注释 |
| `mclby201` | 满程量20备用记录1（视图标签：满量程的20％） | 实体注释 |
| `mclby202` | 满程量20备用记录2（视图标签：满量程的20％） | 实体注释 |
| `mclby401` | 满程量40备用记录1（视图标签：满量程的40％） | 实体注释 |
| `mclby402` | 满程量40备用记录2（视图标签：满量程的40％） | 实体注释 |
| `mclby601` | 满程量60备用记录1（视图标签：满量程的60％） | 实体注释 |
| `mclby602` | 满程量60备用记录2（视图标签：满量程的60％） | 实体注释 |
| `mclby801` | 满程量80备用记录1（视图标签：满量程的80％） | 实体注释 |
| `mclby802` | 满程量80备用记录2（视图标签：满量程的80％） | 实体注释 |
| `starttime` | 起始时间 / 结束时间 | cshtml 标签 |
| `lingdianbz` | 零点标准值 | 实体注释 |
| `lingdianxy` | 零点响应值 | 实体注释 |
| `gassourceno` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `lingdianby1` | 零点备用记录1 | 实体注释 |
| `lingdianby2` | 零点备用记录2 | 实体注释 |
| `devicenameno` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `mcledtdate10` | 满程量10结束时间（视图标签：满量程的10％） | 实体注释 |
| `mcledtdate20` | 满程量20结束时间（视图标签：满量程的20％） | 实体注释 |
| `mcledtdate40` | 满程量40结束时间（视图标签：满量程的40％） | 实体注释 |
| `mcledtdate60` | 满程量60结束时间（视图标签：满量程的60％） | 实体注释 |
| `mcledtdate80` | 满程量80结束时间（视图标签：满量程的80％） | 实体注释 |
| `mclsdtdate10` | 满程量10开始时间（视图标签：满量程的10％） | 实体注释 |
| `mclsdtdate20` | 满程量20开始时间（视图标签：满量程的20％） | 实体注释 |
| `mclsdtdate40` | 满程量40开始时间（视图标签：满量程的40％） | 实体注释 |
| `mclsdtdate60` | 满程量60开始时间（视图标签：满量程的60％） | 实体注释 |
| `mclsdtdate80` | 满程量80开始时间（视图标签：满量程的80％） | 实体注释 |
| `calibrationno` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `integratedtemp` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `calibrationdate` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `lingdianedtdate` | 零点结束始时间 | 实体注释 |
| `lingdiansdtdate` | 零点开始时间 | 实体注释 |
| `gasexpirationdate` | 标气有效期 / 仪器满量程 | cshtml 标签 |

**平台校验器：**`calibrationno`=required；`devicenameno`=required；`gasmic`=required；`gassourceno`=required；`integratedtemp`=required；`lingdianbz`=required；`mclbz10`=required；`mclbz20`=required；`mclbz40`=required；`mclbz60`=required；`mclbz80`=required；`ppb`=required


## Sup_RF_NH3GASEOUSCALIDEVICECHECK（sup_rf_nh3gaseouscalidevicecheck）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3GASEOUSCALIDEVICECHECK`、视图 `Sup_RF_NH3GASEOUSCALIDEVICECHECK.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `qy` | 气压（视图标签：气压 / 温度 / 湿度） | 实体注释 |
| `sd` | 湿度（视图标签：气压 / 温度 / 湿度） | 实体注释 |
| `wd` | 温度（视图标签：气压 / 温度 / 湿度） | 实体注释 |
| `jua1` | 截距a1（视图标签：斜率b= / 截距a= / 相关系数r=） | 实体注释 |
| `jua2` | 截距a2（视图标签：斜率b=） | 实体注释 |
| `xlb1` | 斜率b1（视图标签：斜率b= / 截距a= / 相关系数r=） | 实体注释 |
| `xlb2` | 斜率b2（视图标签：100 ml/min） | 实体注释 |
| `xgxsr1` | 相关系数r1（视图标签：斜率b= / 截距a= / 相关系数r=） | 实体注释 |
| `xgxsr2` | 相关系数r2（视图标签：斜率b= / 截距a=） | 实体注释 |
| `yqdsrow1` | 第一行仪器读数（视图标签：1 / 1 L/min） | 实体注释 |
| `yqdsrow2` | 第二行仪器读数（视图标签：2 / 2 L/min） | 实体注释 |
| `yqdsrow3` | 第三行仪器读数（视图标签：3 / 3 L/min） | 实体注释 |
| `yqdsrow4` | 第四行仪器读数（视图标签：4 / 4 L/min） | 实体注释 |
| `yqdsrow5` | 第五行仪器读数（视图标签：5 / 5 L/min） | 实体注释 |
| `yqdsrow6` | 第六行仪器读数（视图标签：6 / 6 L/min） | 实体注释 |
| `yqdsrow7` | 第七行仪器读数（视图标签：7 / 7 L/min） | 实体注释 |
| `yqdsrow8` | 第八行仪器读数（视图标签：8 / 8 L/min） | 实体注释 |
| `yqdsrow9` | 第九行仪器读数（视图标签：9 / 9 L/min） | 实体注释 |
| `jzlljcode` | 校准流量计编号（视图标签：校准流量计型号 / 校准流量计编号） | 实体注释 |
| `lljdsrow1` | 第一行流量计读数（视图标签：1 / 1 L/min） | 实体注释 |
| `lljdsrow2` | 第二行流量计读数（视图标签：2 / 2 L/min） | 实体注释 |
| `lljdsrow3` | 第三行流量计读数（视图标签：3 / 3 L/min） | 实体注释 |
| `lljdsrow4` | 第四行流量计读数（视图标签：4 / 4 L/min） | 实体注释 |
| `lljdsrow5` | 第五行流量计读数（视图标签：5 / 5 L/min） | 实体注释 |
| `lljdsrow6` | 第六行流量计读数（视图标签：6 / 6 L/min） | 实体注释 |
| `lljdsrow7` | 第七行流量计读数（视图标签：7 / 7 L/min） | 实体注释 |
| `lljdsrow8` | 第八行流量计读数（视图标签：8 / 8 L/min） | 实体注释 |
| `lljdsrow9` | 第九行流量计读数（视图标签：9 / 9 L/min） | 实体注释 |
| `lljxzrow1` | 第一行流量计修正读数（视图标签：1 / 1 L/min） | 实体注释 |
| `lljxzrow2` | 第二行流量计修正读数（视图标签：2 / 2 L/min） | 实体注释 |
| `lljxzrow3` | 第三行流量计修正读数（视图标签：3 / 3 L/min） | 实体注释 |
| `lljxzrow4` | 第四行流量计修正读数（视图标签：4 / 4 L/min） | 实体注释 |
| `lljxzrow5` | 第五行流量计修正读数（视图标签：5 / 5 L/min） | 实体注释 |
| `lljxzrow6` | 第六行流量计修正读数（视图标签：6 / 6 L/min） | 实体注释 |
| `lljxzrow7` | 第七行流量计修正读数（视图标签：7 / 7 L/min） | 实体注释 |
| `lljxzrow8` | 第八行流量计修正读数（视图标签：8 / 8 L/min） | 实体注释 |
| `lljxzrow9` | 第九行流量计修正读数（视图标签：9 / 9 L/min） | 实体注释 |
| `syjzqrow1` | 第一行输入校准器值（视图标签：1 / 1 L/min） | 实体注释 |
| `syjzqrow2` | 第三行输入校准器值（视图标签：2 / 2 L/min） | 实体注释 |
| `syjzqrow3` | 第三行输入校准器值（视图标签：3 / 3 L/min） | 实体注释 |
| `syjzqrow4` | 第四行输入校准器值（视图标签：4 / 4 L/min） | 实体注释 |
| `syjzqrow5` | 第五行输入校准器值（视图标签：5 / 5 L/min） | 实体注释 |
| `syjzqrow6` | 第六行输入校准器值（视图标签：6 / 6 L/min） | 实体注释 |
| `syjzqrow7` | 第七行输入校准器值（视图标签：7 / 7 L/min） | 实体注释 |
| `syjzqrow8` | 第八行输入校准器值（视图标签：8 / 8 L/min） | 实体注释 |
| `syjzqrow9` | 第九行输入校准器值（视图标签：9 / 9 L/min） | 实体注释 |
| `yqdsrow10` | 第十行仪器读数（视图标签：10 / 10 L/min） | 实体注释 |
| `jzlljmodel` | 校准流量计型号（视图标签：校准流量计型号 / 校准流量计编号） | 实体注释 |
| `lljdsrow10` | 第十行流量计读数（视图标签：10 / 10 L/min） | 实体注释 |
| `lljxzrow10` | 第十行流量计修正读数（视图标签：10 / 10 L/min） | 实体注释 |
| `llkzqrow11` | 第一行一列流量控制器（视图标签：1 / 10 ml/min） | 实体注释 |
| `llkzqrow12` | 第一行二列流量控制器（视图标签：1 / 10 ml/min） | 实体注释 |
| `llkzqrow13` | 第一行三列流量控制器（视图标签：1 / 10 ml/min） | 实体注释 |
| `llkzqrow14` | 第一行四列流量控制器（视图标签：1 / 10 ml/min） | 实体注释 |
| `llkzqrow21` | 第二行一列流量控制器（视图标签：2 / 20 ml/min） | 实体注释 |
| `llkzqrow22` | 第二行二列流量控制器（视图标签：2 / 20 ml/min） | 实体注释 |
| `llkzqrow23` | 第二行三列流量控制器（视图标签：2 / 20 ml/min） | 实体注释 |
| `llkzqrow24` | 第二行四列流量控制器（视图标签：2 / 20 ml/min） | 实体注释 |
| `llkzqrow31` | 第三行一列流量控制器（视图标签：3 / 30 ml/min） | 实体注释 |
| `llkzqrow32` | 第三行二列流量控制器（视图标签：3 / 30 ml/min） | 实体注释 |
| `llkzqrow33` | 第三行三列流量控制器（视图标签：3 / 30 ml/min） | 实体注释 |
| `llkzqrow34` | 第三行四列流量控制器（视图标签：3 / 30 ml/min） | 实体注释 |
| `llkzqrow41` | 第四行一列流量控制器（视图标签：4 / 40 ml/min） | 实体注释 |
| `llkzqrow42` | 第四行二列流量控制器（视图标签：4 / 40 ml/min） | 实体注释 |
| `llkzqrow43` | 第四行三列流量控制器（视图标签：4 / 40 ml/min） | 实体注释 |
| `llkzqrow44` | 第四行四列流量控制器（视图标签：4 / 40 ml/min） | 实体注释 |
| `llkzqrow51` | 第五行一列流量控制器（视图标签：5 / 50 ml/min） | 实体注释 |
| `llkzqrow52` | 第五行二列流量控制器（视图标签：5 / 50 ml/min） | 实体注释 |
| `llkzqrow53` | 第五行三列流量控制器（视图标签：5 / 50 ml/min） | 实体注释 |
| `llkzqrow54` | 第五行四列流量控制器（视图标签：5 / 50 ml/min） | 实体注释 |
| `llkzqrow61` | 第六行一列流量控制器（视图标签：6 / 60 ml/min） | 实体注释 |
| `llkzqrow62` | 第六行二列流量控制器（视图标签：6 / 60 ml/min） | 实体注释 |
| `llkzqrow63` | 第六行三列流量控制器（视图标签：6 / 60 ml/min） | 实体注释 |
| `llkzqrow64` | 第六行四列流量控制器（视图标签：6 / 60 ml/min） | 实体注释 |
| `llkzqrow71` | 第七行一列流量控制器（视图标签：7 / 70 ml/min） | 实体注释 |
| `llkzqrow72` | 第七行二列流量控制器（视图标签：7 / 70 ml/min） | 实体注释 |
| `llkzqrow73` | 第七行三列流量控制器（视图标签：7 / 70 ml/min） | 实体注释 |
| `llkzqrow74` | 第七行四列流量控制器（视图标签：7 / 70 ml/min） | 实体注释 |
| `llkzqrow81` | 第八行一列流量控制器（视图标签：8 / 80 ml/min） | 实体注释 |
| `llkzqrow82` | 第八行二列流量控制器（视图标签：8 / 80 ml/min） | 实体注释 |
| `llkzqrow83` | 第八行三列流量控制器（视图标签：8 / 80 ml/min） | 实体注释 |
| `llkzqrow84` | 第八行四列流量控制器（视图标签：8 / 80 ml/min） | 实体注释 |
| `llkzqrow91` | 第九行一列流量控制器（视图标签：9 / 90 ml/min） | 实体注释 |
| `llkzqrow92` | 第九行二列流量控制器（视图标签：9 / 90 ml/min） | 实体注释 |
| `llkzqrow93` | 第九行三列流量控制器（视图标签：9 / 90 ml/min） | 实体注释 |
| `llkzqrow94` | 第九行四列流量控制器（视图标签：9 / 90 ml/min） | 实体注释 |
| `syjzqrow10` | 第十行输入校准器值（视图标签：10 / 10 L/min） | 实体注释 |
| `llkzqrow101` | 第十行一列流量控制器（视图标签：10 / 100 ml/min） | 实体注释 |
| `llkzqrow102` | 第十行二列流量控制器（视图标签：10 / 100 ml/min） | 实体注释 |
| `llkzqrow103` | 第十行三列流量控制器（视图标签：10 / 100 ml/min） | 实体注释 |
| `llkzqrow104` | 第十行四列流量控制器（视图标签：10 / 100 ml/min） | 实体注释 |
| `checkdateself` | 检查时间（视图标签：仪器型号/编号 / 检查时间） | 实体注释 |
| `devicemodelcode` | 设备型号/编号（视图标签：仪器型号/编号 / 检查时间） | 实体注释 |


## Sup_RF_NH3InstrumentDetectionLimit（sup_rf_nh3instrumentdetectionlimit）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3InstrumentDetectionLimit`、视图 `Sup_RF_NH3InstrumentDetectionLimit.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `dev` | 标准偏差 | cshtml 标签 |
| `ppb` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `idls` | 仪器检出限 | cshtml 标签 |
| `gasmic` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `endtime` | 起始时间 / 结束时间 | cshtml 标签 |
| `remark1` | 备注： | cshtml 标签 |
| `starttime` | 起始时间 / 结束时间 | cshtml 标签 |
| `gassourceno` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `devicenameno` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `calibrationno` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `integratedtemp` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `calibrationdate` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `calibrationresult` | 校准结果 | cshtml 标签 |
| `gasexpirationdate` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `passgasconcentrations` | 通入标气浓度 | cshtml 标签 |
| `instrumentresponsevalues1` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues2` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues3` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues4` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues5` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues6` | 仪器响应值 | cshtml 标签 |

**平台校验器：**`calibrationno`=required；`dev`=required；`devicenameno`=required；`gasmic`=required；`gassourceno`=required；`idls`=required；`instrumentresponsevalues1`=required；`instrumentresponsevalues2`=required；`instrumentresponsevalues3`=required；`instrumentresponsevalues4`=required；`instrumentresponsevalues5`=required；`instrumentresponsevalues6`=required；`integratedtemp`=required；`passgasconcentrations`=required；`ppb`=required


## Sup_RF_NH3InstrumentPrecision（sup_rf_nh3instrumentprecision）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3InstrumentPrecision`、视图 `Sup_RF_NH3InstrumentPrecision.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `ppb` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `rsd` | 相对标准偏差 | cshtml 标签 |
| `gasmic` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `endtime` | 起始时间 / 结束时间 | cshtml 标签 |
| `remark1` | 备注： | cshtml 标签 |
| `accuracy` | 响应均值 / 正确度% | cshtml 标签 |
| `starttime` | 起始时间 / 结束时间 | cshtml 标签 |
| `gassourceno` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `devicenameno` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `calibrationno` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `integratedtemp` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `calibrationdate` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `calibrationresult` | 校准结果 | cshtml 标签 |
| `gasexpirationdate` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `gasconcentration20` | 通标气浓度(20%量程) | cshtml 标签 |
| `instrumentresponseavg` | 响应均值 / 正确度% | cshtml 标签 |
| `instrumentresponsevalues1` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues2` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues3` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues4` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues5` | 仪器响应值 | cshtml 标签 |
| `instrumentresponsevalues6` | 仪器响应值 | cshtml 标签 |

**平台校验器：**`accuracy`=required；`calibrationno`=required；`devicenameno`=required；`gasconcentration20`=required；`gasmic`=required；`gassourceno`=required；`instrumentresponseavg`=required；`instrumentresponsevalues1`=required；`instrumentresponsevalues2`=required；`instrumentresponsevalues3`=required；`instrumentresponsevalues4`=required；`instrumentresponsevalues5`=required；`instrumentresponsevalues6`=required；`integratedtemp`=required；`ppb`=required；`rsd`=required


## Sup_RF_NH3MonthDeviceMaintain（sup_rf_nh3monthdevicemaintain）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3MonthDeviceMaintain`、视图 `Sup_RF_NH3MonthDeviceMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `datetime1` | 1 / 每月清洗一次制冷系统过滤网 | cshtml 标签 |
| `datetime2` | 2 / 每月清洁仪器风扇防尘网 | cshtml 标签 |
| `datetime3` | 3 / 仪器时钟检查;数据采集仪时钟检查 | cshtml 标签 |
| `datetime4` | 4 / 仪器显示数据和数据采集仪之间的一致性检查 | cshtml 标签 |
| `datetime5` | 5 / 检查设备电机运转情况 | cshtml 标签 |


## Sup_RF_NH3ResponseTimeInspection（sup_rf_nh3responsetimeinspection）
- 《组分仪器工单规则》：颗粒物组分/NH3分析仪.docx
- 源码依据：实体 `Sup_RF_NH3ResponseTimeInspection`、视图 `Sup_RF_NH3ResponseTimeInspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `ppb` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `gasmic` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `endtime` | 起始时间 / 结束时间 | cshtml 标签 |
| `remark1` | 备注： | cshtml 标签 |
| `starttime` | 起始时间 / 结束时间 | cshtml 标签 |
| `stabletime` | 响应时间T90上升 / 稳定时间Tme | cshtml 标签 |
| `gassourceno` | 标气来源及编号 / 标气浓度 | cshtml 标签 |
| `devicenameno` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `calibrationno` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `calibratormic` | 校准仪输出浓度 / 仪器初试显值 | cshtml 标签 |
| `integratedtemp` | 校准仪编号 / 站房温湿度/气压 | cshtml 标签 |
| `calibrationdate` | 仪器名称及编号 / 校准日期 | cshtml 标签 |
| `fallbacktimet10` | 最终稳定显值 / 回降时间T10 | cshtml 标签 |
| `responsetimet90` | 响应时间T90上升 / 稳定时间Tme | cshtml 标签 |
| `calibrationresult` | 校准结果 | cshtml 标签 |
| `gasexpirationdate` | 标气有效期 / 仪器满量程 | cshtml 标签 |
| `finallystablevalues` | 最终稳定显值 / 回降时间T10 | cshtml 标签 |
| `instrumentinitvalue` | 校准仪输出浓度 / 仪器初试显值 | cshtml 标签 |

**平台校验器：**`calibrationno`=required；`calibratormic`=required；`devicenameno`=required；`finallystablevalues`=required；`gasmic`=required；`gassourceno`=required；`instrumentinitvalue`=required；`integratedtemp`=required；`ppb`=required；`responsetimet90`=required


## Sup_RF_NMHCAnalyzerRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/甲烷非甲烷.docx
- 源码依据：实体 `Sup_RF_NMHCAnalyzerRecord`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次校准日期 | 实体注释 |
| `time2` | 参考流量计 - 下一次校准日期 | 实体注释 |
| `time3` | OCEC分析仪资料 - 上一次校准时间 | 实体注释 |
| `time4` | OCEC分析仪资料 - 下一次校准时间 | 实体注释 |
| `string1` | 设备型号 | 实体注释 |
| `string2` | 出厂编号 | 实体注释 |
| `string3` | 斜率 | 实体注释 |
| `string4` | 截距 | 实体注释 |
| `string5` | 相关系数 | 实体注释 |
| `string6` | 仪器型号 | 实体注释 |
| `string7` | 出厂编号 | 实体注释 |
| `string8` | 监测项目 | 实体注释 |
| `string9` | 设定流量 - 氦气 | 实体注释 |
| `string10` | 显示流量 - 氦气 | 实体注释 |
| `string11` | 参考流量计读数 - 氦气 | 实体注释 |
| `string12` | 参考流量计修正 - 氦气 | 实体注释 |
| `string13` | 误差 - 氦气 | 实体注释 |
| `string14` | 检查结果 - 氦气 | 实体注释 |
| `string15` | 设定流量 - 氦气（吹扫） | 实体注释 |
| `string16` | 显示流量 - 氦气（吹扫） | 实体注释 |
| `string17` | 参考流量计读数 - 氦气（吹扫） | 实体注释 |
| `string18` | 参考流量计修正 - 氦气（吹扫） | 实体注释 |
| `string19` | 误差 - 氦气（吹扫） | 实体注释 |
| `string20` | 检查结果 - 氦气（吹扫） | 实体注释 |
| `string21` | 设定流量 - 氦氧 | 实体注释 |
| `string22` | 显示流量 - 氦氧 | 实体注释 |
| `string23` | 参考流量计读数 - 氦氧 | 实体注释 |
| `string24` | 参考流量计修正 - 氦氧 | 实体注释 |
| `string25` | 误差 - 氦氧 | 实体注释 |
| `string26` | 检查结果 - 氦氧 | 实体注释 |
| `string27` | 设定流量 - 氦甲烷 | 实体注释 |
| `string28` | 显示流量 - 氦甲烷 | 实体注释 |
| `string29` | 参考流量计读数 - 氦甲烷 | 实体注释 |
| `string30` | 参考流量计修正 - 氦甲烷 | 实体注释 |
| `string31` | 误差 - 氦甲烷 | 实体注释 |
| `string32` | 检查结果 - 氦甲烷 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_NepheloMeterCalibration（sup_rf_nephelometercalibration）
- 《组分仪器工单规则》：颗粒物组分/浊度计.docx
- 源码依据：实体 `Sup_RF_NepheloMeterCalibration`、视图 `Sup_RF_NepheloMeterCalibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `b1` | （视图标签：σ450 / 0.00（A）） | 实体注释 |
| `b2` | （视图标签：σ525 / 0.00（A）） | 实体注释 |
| `b3` | （视图标签：σ630 / 0.00（A）） | 实体注释 |
| `b4` | （视图标签：σ450 / 174.37） | 实体注释 |
| `b5` | （视图标签：σ525 / 94.11） | 实体注释 |
| `b6` | （视图标签：σ630 / 43.97） | 实体注释 |
| `c1` | （视图标签：σ450 / 0.00（A）） | 实体注释 |
| `c2` | （视图标签：σ525 / 0.00（A）） | 实体注释 |
| `c3` | （视图标签：σ630 / 0.00（A）） | 实体注释 |
| `c4` | （视图标签：σ450 / 174.37） | 实体注释 |
| `c5` | （视图标签：σ525 / 94.11） | 实体注释 |
| `c6` | （视图标签：σ630 / 43.97） | 实体注释 |
| `bz1` | （视图标签：σ450 / 0.00（A）） | 实体注释 |
| `bz2` | （视图标签：σ525 / 0.00（A）） | 实体注释 |
| `bz3` | （视图标签：σ630 / 0.00（A）） | 实体注释 |
| `bz4` | （视图标签：σ450 / 174.37） | 实体注释 |
| `bz5` | （视图标签：σ525 / 94.11） | 实体注释 |
| `bz6` | （视图标签：σ630 / 43.97） | 实体注释 |
| `jzh1` | （视图标签：σ450 / 0.00（A）） | 实体注释 |
| `jzh2` | （视图标签：σ525 / 0.00（A）） | 实体注释 |
| `jzh3` | （视图标签：σ630 / 0.00（A）） | 实体注释 |
| `jzh4` | （视图标签：σ450 / 174.37） | 实体注释 |
| `jzh5` | （视图标签：σ525 / 94.11） | 实体注释 |
| `jzh6` | （视图标签：σ630 / 43.97） | 实体注释 |


## Sup_RF_O3LaserRadarCalibration（sup_rf_o3laserradarcalibration）
- 《组分仪器工单规则》：光化学组分/臭氧激光雷达.docx + 颗粒物组分/颗粒物激光雷达.docx
- 源码依据：实体 `Sup_RF_O3LaserRadarCalibration`、视图 `Sup_RF_O3LaserRadarCalibration.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `other_1_2` | 其他 / 采集软件回波曲线绘制 | cshtml 标签 |
| `other_2_2` | 采集软件日志查询 | cshtml 标签 |
| `other_3_2` | 采集软件设备状态显示 | cshtml 标签 |
| `other_4_2` | 分析软件各个图谱自动绘制 | cshtml 标签 |
| `other_5_2` | 分析软件报表、图谱导出及传输 | cshtml 标签 |
| `other_6_2` | 分析软件参数设置 | cshtml 标签 |
| `other_7_2` | 数据系统线性度 | cshtml 标签 |
| `other_8_2` | 信噪比 | cshtml 标签 |
| `other_9_2` | 有效探测距离 | cshtml 标签 |
| `weatherenv_1` | 天气环境 / 天气情况 | cshtml 标签 |
| `weatherenv_4` | 空气质量等级 | cshtml 标签 |
| `receivesystem_1_2` | 接收系统 / 天窗窗口表面是否有灰尘积累、污脏 | cshtml 标签 |
| `receivesystem_2_2` | 防护镜灰尘是否清理 | cshtml 标签 |
| `launchingsystem_1_2` | 激光光斑位于天窗出光孔中心 | cshtml 标签 |
| `launchingsystem_2_2` | 激光器是否有异常报警 | cshtml 标签 |
| `launchingsystem_3_2` | 激光器冷却水水位是否高于最低水位线（仅限水冷激光器） | cshtml 标签 |
| `launchingsystem_4_2` | 激光器电源水温是否正常（10-40℃）（仅限水冷激光器） | cshtml 标签 |
| `launchingsystem_5_2` | 更换一次冷却水（仅限水冷激光器） | cshtml 标签 |
| `launchingsystem_6_2` | 更换一次冷却水滤芯（仅限水冷激光器） | cshtml 标签 |
| `datacollectsystem_1_2` | 数据采集处理系统 / 采集软件回波曲线绘制 | cshtml 标签 |
| `datacollectsystem_2_2` | 采集软件日志查询 | cshtml 标签 |
| `datacollectsystem_3_2` | 采集软件设备状态显示 | cshtml 标签 |
| `datacollectsystem_4_2` | 分析软件各个图谱自动绘制 | cshtml 标签 |
| `datacollectsystem_5_2` | 分析软件报表、图谱导出及传输 | cshtml 标签 |
| `datacollectsystem_6_2` | 分析软件参数设置 | cshtml 标签 |
| `datacollectsystem_7_2` | 数据系统线性度 | cshtml 标签 |
| `datacollectsystem_8_2` | 信噪比 | cshtml 标签 |
| `datacollectsystem_9_2` | 有效探测距离 | cshtml 标签 |
| `datacollectsystem_10_2` | 有效数据率（不低于85%） | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_O3LaserRadarCalibration_PMLidar.vue）：**

string1 至 string4 为天气环境；bool_1 至 bool_27、string5 至 string31 为 27 项设备核查结果及详细数据； remark 为备注；commonFile 为整表附件。


## Sup_RF_O3LaserRadarCheck（sup_rf_o3laserradarcheck）
- 《组分仪器工单规则》：光化学组分/臭氧激光雷达.docx + 颗粒物组分/颗粒物激光雷达.docx
- 源码依据：实体 `Sup_RF_O3LaserRadarCheck`、视图 `Sup_RF_O3LaserRadarCheck.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `laser_1_2` | 激光雷达激光器电源水位在正常位以上 | cshtml 标签 |
| `laser_2_2` | 激光雷达防护镜灰尘是否清理 | cshtml 标签 |
| `laser_3_2` | 激光雷达激光光斑位于天窗出光孔中心 | cshtml 标签 |
| `laser_4_2` | 激光器电源水温【10－40】℃ | cshtml 标签 |
| `collect_1_2` | 采集 / 回波曲线绘制 | cshtml 标签 |
| `skylight_1_2` | 天窗 / 天窗洁净 | cshtml 标签 |
| `skylight_2_2` | 天窗加热 | cshtml 标签 |
| `software_1_2` | 软件 / 日志查询 | cshtml 标签 |
| `software_2_2` | 设备状态显示 | cshtml 标签 |
| `sensirion_1_2` | 温湿度传感器 / 室外温湿度监测 | cshtml 标签 |
| `analysissoftware_1_2` | 分析软件 / 各个图谱自动绘制 | cshtml 标签 |
| `analysissoftware_2_2` | 报表、图谱导出 | cshtml 标签 |
| `analysissoftware_3_2` | 参数设置 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_O3LaserRadarCheck_PMLidar.vue）：**

bool_1 至 bool_15 为站房外部及内部检查；bool_16 至 bool_28、string1 至 string13 为设备检查结果和详细数据； remark 为异常情况及处理说明；commonFile 为整表附件。

**平台校验器：**`analysissoftware_1_2`=required；`analysissoftware_2_2`=required；`analysissoftware_3_2`=required；`collect_1_2`=required；`laser_1_2`=required；`laser_2_2`=required；`laser_3_2`=required；`laser_4_2`=required；`sensirion_1_2`=required；`skylight_1_2`=required；`skylight_2_2`=required；`software_1_2`=required；`software_2_2`=required


## Sup_RF_O3LaserRadarMaintenance（sup_rf_o3laserradarmaintenance）
- 《组分仪器工单规则》：光化学组分/臭氧激光雷达.docx + 颗粒物组分/颗粒物激光雷达.docx
- 源码依据：实体 `Sup_RF_O3LaserRadarMaintenance`、视图 `Sup_RF_O3LaserRadarMaintenance.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `cleandevicefantime` | 2 / 每月清洁仪器风扇防尘网 | cshtml 标签 |
| `cleancoldsystemscreentime` | 1 / 每月清洗一次制冷系统过滤网 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_O3LaserRadarMaintenance_PMLidar.vue）：**

time1、time2 为两项维护时间；string1、string2 为巡检人签字；remark 为异常情况；commonFile 为整表附件。


## Sup_RF_O3LidarRepair（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/臭氧激光雷达.docx + 颗粒物组分/颗粒物激光雷达.docx
- 源码依据：实体 `Sup_RF_O3LidarRepair`、视图 `Sup_RF_O3LidarRepair.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `string1` | 检修分析仪型号/编号 | cshtml 标签 |
| `string2` | 检修时间 | cshtml 标签 |
| `string3` | 故障现象 | cshtml 标签 |
| `string4` | 故障原因和检修过程 | cshtml 标签 |
| `string5` | 更换零件名称 | cshtml 标签 |
| `string6` | 维修结果 | cshtml 标签 |
| `remark50` | 备注： | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_O3LidarRepair_O3Lidar.vue）：**

string1 至 string6 为检修记录内容；remark 为总备注；commonFile 为附件。

**平台校验器：**`string1`=required；`string2`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required


## Sup_RF_OCECHalfYearCheck（sup_rf_ocechalfyearcheck）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECHalfYearCheck`、视图 `Sup_RF_OCECHalfYearCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bz` | （视图标签：1 / 采样管清洁） | 实体注释 |
| `nr` | （视图标签：1 / 采样管清洁） | 实体注释 |
| `threepeak_sd_1` | 1 | cshtml 标签 |
| `threepeak_sd_2` | 2 | cshtml 标签 |
| `threepeak_sd_3` | 3 | cshtml 标签 |
| `threepeak_rsd_1` | 1 | cshtml 标签 |
| `threepeak_rsd_2` | 2 | cshtml 标签 |
| `threepeak_rsd_3` | 3 | cshtml 标签 |
| `threepeak_aerobic_1` | 1 | cshtml 标签 |
| `threepeak_aerobic_2` | 2 | cshtml 标签 |
| `threepeak_aerobic_3` | 3 | cshtml 标签 |
| `threepeak_average_1` | 1 | cshtml 标签 |
| `threepeak_average_2` | 2 | cshtml 标签 |
| `threepeak_average_3` | 3 | cshtml 标签 |
| `threepeak_anaerobic_1` | 1 | cshtml 标签 |
| `threepeak_anaerobic_2` | 2 | cshtml 标签 |
| `threepeak_anaerobic_3` | 3 | cshtml 标签 |
| `threepeak_isqualified_1` | 1 | cshtml 标签 |
| `threepeak_isqualified_2` | 2 | cshtml 标签 |
| `threepeak_isqualified_3` | 3 | cshtml 标签 |
| `threepeak_internalstandard_1` | 1 | cshtml 标签 |
| `threepeak_internalstandard_2` | 2 | cshtml 标签 |
| `threepeak_internalstandard_3` | 3 | cshtml 标签 |

**平台校验器：**`bz`=required；`threepeak_aerobic_1`=required；`threepeak_aerobic_2`=required；`threepeak_aerobic_3`=required；`threepeak_anaerobic_1`=required；`threepeak_anaerobic_2`=required；`threepeak_anaerobic_3`=required；`threepeak_average_1`=required；`threepeak_average_2`=required；`threepeak_average_3`=required；`threepeak_internalstandard_1`=required；`threepeak_internalstandard_2`=required；`threepeak_internalstandard_3`=required；`threepeak_rsd_1`=required；`threepeak_rsd_2`=required；`threepeak_rsd_3`=required；`threepeak_sd_1`=required；`threepeak_sd_2`=required；`threepeak_sd_3`=required


## Sup_RF_OCECJGMultipointCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECJGMultipointCheck`、视图 `Sup_RF_OCECJGMultipointCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 标准蔗糖溶液配制日期（视图标签：配制日期 / 有效期限） | 实体注释 |
| `time2` | 标准蔗糖溶液有效期限（视图标签：配制日期 / 有效期限） | 实体注释 |
| `time3` | 分析仪资料上一次核查日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time4` | 分析仪资料下一次核查日期（视图标签：上一次 / 下一次） | 实体注释 |
| `string1` | 标准溶液浓度（视图标签：配制日期 / 有效期限） | 实体注释 |
| `string2` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string3` | 出厂编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string4` | 空白 | cshtml 标签 |
| `string5` | 空白 | cshtml 标签 |
| `string6` | 空白 | cshtml 标签 |
| `string7` | 空白 | cshtml 标签 |
| `string8` | 空白 | cshtml 标签 |
| `string9` | 空白 | cshtml 标签 |
| `string10` | （视图绑定，含义见标签） | cshtml 标签 |
| `string11` | （视图绑定，含义见标签） | cshtml 标签 |
| `string12` | （视图绑定，含义见标签） | cshtml 标签 |
| `string13` | （视图绑定，含义见标签） | cshtml 标签 |
| `string14` | 曲线点1 | cshtml 标签 |
| `string15` | 曲线点1 | cshtml 标签 |
| `string16` | 曲线点1 | cshtml 标签 |
| `string17` | 曲线点1 | cshtml 标签 |
| `string18` | 曲线点1 | cshtml 标签 |
| `string19` | 曲线点1 | cshtml 标签 |
| `string20` | 曲线点1 | cshtml 标签 |
| `string21` | 曲线点1 | cshtml 标签 |
| `string22` | 曲线点1 | cshtml 标签 |
| `string23` | 曲线点1 | cshtml 标签 |
| `string24` | 曲线点1 | cshtml 标签 |
| `string25` | （视图绑定，含义见标签） | cshtml 标签 |
| `string26` | （视图绑定，含义见标签） | cshtml 标签 |
| `string27` | （视图绑定，含义见标签） | cshtml 标签 |
| `string28` | （视图绑定，含义见标签） | cshtml 标签 |
| `string29` | （视图绑定，含义见标签） | cshtml 标签 |
| `string30` | 曲线点2 | cshtml 标签 |
| `string31` | 曲线点2 | cshtml 标签 |
| `string32` | 曲线点2 | cshtml 标签 |
| `string33` | 曲线点2 | cshtml 标签 |
| `string34` | 曲线点2 | cshtml 标签 |
| `string35` | 曲线点2 | cshtml 标签 |
| `string36` | 曲线点2 | cshtml 标签 |
| `string37` | 曲线点2 | cshtml 标签 |
| `string38` | 曲线点2 | cshtml 标签 |
| `string39` | 曲线点2 | cshtml 标签 |
| `string40` | 曲线点2 | cshtml 标签 |
| `string41` | （视图绑定，含义见标签） | cshtml 标签 |
| `string42` | （视图绑定，含义见标签） | cshtml 标签 |
| `string43` | （视图绑定，含义见标签） | cshtml 标签 |
| `string44` | （视图绑定，含义见标签） | cshtml 标签 |
| `string45` | （视图绑定，含义见标签） | cshtml 标签 |
| `string46` | 曲线点3 | cshtml 标签 |
| `string47` | 曲线点3 | cshtml 标签 |
| `string48` | 曲线点3 | cshtml 标签 |
| `string49` | 曲线点3 | cshtml 标签 |
| `string50` | 曲线点3 | cshtml 标签 |
| `string51` | 曲线点3 | cshtml 标签 |
| `string52` | 曲线点3 | cshtml 标签 |
| `string53` | 曲线点3 | cshtml 标签 |
| `string54` | 曲线点3 | cshtml 标签 |
| `string55` | 曲线点3 | cshtml 标签 |
| `string56` | 曲线点3 | cshtml 标签 |
| `string57` | （视图绑定，含义见标签） | cshtml 标签 |
| `string58` | （视图绑定，含义见标签） | cshtml 标签 |
| `string59` | （视图绑定，含义见标签） | cshtml 标签 |
| `string60` | （视图绑定，含义见标签） | cshtml 标签 |
| `string61` | （视图绑定，含义见标签） | cshtml 标签 |
| `string62` | 曲线点4 | cshtml 标签 |
| `string63` | 曲线点4 | cshtml 标签 |
| `string64` | 曲线点4 | cshtml 标签 |
| `string65` | 曲线点4 | cshtml 标签 |
| `string66` | 曲线点4 | cshtml 标签 |
| `string67` | 曲线点4 | cshtml 标签 |
| `string68` | 曲线点4 | cshtml 标签 |
| `string69` | 曲线点4 | cshtml 标签 |
| `string70` | 曲线点4 | cshtml 标签 |
| `string71` | 曲线点4 | cshtml 标签 |
| `string72` | 曲线点4 | cshtml 标签 |
| `string73` | （视图绑定，含义见标签） | cshtml 标签 |
| `string74` | （视图绑定，含义见标签） | cshtml 标签 |
| `string75` | （视图绑定，含义见标签） | cshtml 标签 |
| `string76` | （视图绑定，含义见标签） | cshtml 标签 |
| `string77` | （视图绑定，含义见标签） | cshtml 标签 |
| `string78` | 曲线点5 | cshtml 标签 |
| `string79` | 曲线点5 | cshtml 标签 |
| `string80` | 曲线点5 | cshtml 标签 |
| `string81` | 曲线点5 | cshtml 标签 |
| `string82` | 曲线点5 | cshtml 标签 |
| `string83` | 曲线点5 | cshtml 标签 |
| `string84` | 曲线点5 | cshtml 标签 |
| `string85` | 曲线点5 | cshtml 标签 |
| `string86` | 曲线点5 | cshtml 标签 |
| `string87` | 曲线点5 | cshtml 标签 |
| `string88` | 曲线点5 | cshtml 标签 |
| `string89` | （视图绑定，含义见标签） | cshtml 标签 |
| `string90` | （视图绑定，含义见标签） | cshtml 标签 |
| `string91` | （视图绑定，含义见标签） | cshtml 标签 |
| `string92` | （视图绑定，含义见标签） | cshtml 标签 |
| `string93` | （视图绑定，含义见标签） | cshtml 标签 |
| `string94` | 旧校准常数（如适用） / / / 曲线斜率 / 相关系数 | cshtml 标签 |
| `string95` | 旧校准常数（如适用） / / / 曲线斜率 / 相关系数 | cshtml 标签 |
| `string96` | 新校准常数（如适用） / / / 曲线截距 / / / / | cshtml 标签 |
| `string97` | 精密度 / 相对标准偏差% / ≤5% | cshtml 标签 |
| `string98` | 正确度 / 相对误差% / 在±10%范围内 | cshtml 标签 |
| `string99` | 系统空白 / （μg/m³） / 应小于1.0μgC/m³ | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string4`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string46`=required；`string47`=required；`string48`=required；`string49`=required；`string5`=required；`string50`=required；`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required；`string56`=required；`string57`=required；`string58`=required；`string59`=required；`string6`=required；`string60`=required；`string61`=required；`string62`=required；`string63`=required；`string64`=required；`string65`=required；`string66`=required；`string67`=required；`string68`=required；`string69`=required；`string7`=required；`string70`=required；`string71`=required；`string72`=required；`string73`=required；`string74`=required；`string75`=required；`string76`=required；`string77`=required；`string78`=required；`string79`=required；`string8`=required；`string80`=required；`string81`=required；`string82`=required；`string83`=required；`string84`=required；`string85`=required；`string86`=required；`string87`=required；`string88`=required；`string89`=required；`string9`=required；`string90`=required；`string91`=required；`string92`=required；`string93`=required；`string94`=required；`string95`=required；`string96`=required；`string97`=required；`string98`=required；`string99`=required


## Sup_RF_OCECJGSingleCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECJGSingleCheck`、视图 `Sup_RF_OCECJGSingleCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 标准蔗糖溶液配制日期（视图标签：配制日期 / 有效期限） | 实体注释 |
| `time2` | 标准蔗糖溶液有效期限（视图标签：配制日期 / 有效期限） | 实体注释 |
| `time3` | 仪器资料上一次核查日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time4` | 仪器资料下一次核查日期（视图标签：上一次 / 下一次） | 实体注释 |
| `string1` | 标准溶液浓度（视图标签：配制日期 / 有效期限） | 实体注释 |
| `string2` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string3` | 出厂编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string4` | 标准碳质量1（视图标签：中间浓度点 / 1） | 实体注释 |
| `string5` | 测量质量1（视图标签：中间浓度点 / 1） | 实体注释 |
| `string6` | 总面积1（视图标签：中间浓度点 / 1） | 实体注释 |
| `string7` | 实际面积1（视图标签：中间浓度点 / 1） | 实体注释 |
| `string8` | 甲烷峰面积1（视图标签：中间浓度点 / 1） | 实体注释 |
| `string9` | 偏差1（视图标签：中间浓度点 / 1） | 实体注释 |
| `string10` | 标准碳质量2 | 实体注释 |
| `string11` | 测量质量2 | 实体注释 |
| `string12` | 总面积2 | 实体注释 |
| `string13` | 实际面积2 | 实体注释 |
| `string14` | 甲烷峰面积2 | 实体注释 |
| `string15` | 偏差2 | 实体注释 |
| `string16` | 标准碳质量3 | 实体注释 |
| `string17` | 测量质量3 | 实体注释 |
| `string18` | 总面积3 | 实体注释 |
| `string19` | 实际面积3 | 实体注释 |
| `string20` | 甲烷峰面积3 | 实体注释 |
| `string21` | 偏差3 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_OCECJGWeekCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECJGWeekCheck`、视图 `Sup_RF_OCECJGWeekCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `string1` | 采样状态下 /// 透射 - 检查值（视图标签：1 / 激光值 / 透射 / // / 0） | 实体注释 |
| `string2` | 透射 - 备注（视图标签：1 / 激光值 / 透射 / // / 0） | 实体注释 |
| `string3` | 反射 - 检查值（视图标签：反射 / 0） | 实体注释 |
| `string4` | 反射 - 备注（视图标签：反射 / 0） | 实体注释 |
| `string5` | 采样流量 - 检查值（视图标签：2 / 采样流量 / L / 8±5%） | 实体注释 |
| `string6` | 采样流量 - 备注（视图标签：2 / 采样流量 / L / 8±5%） | 实体注释 |
| `string7` | 腔体压力 - 检查值（视图标签：3 / 腔体压力 / kPa / 50~80） | 实体注释 |
| `string8` | 腔体压力 - 备注（视图标签：3 / 腔体压力 / kPa / 50~80） | 实体注释 |
| `string9` | He主吹 - 检查值（视图标签：4 / He主吹 / cc/min / 0） | 实体注释 |
| `string10` | He主吹 - 备注（视图标签：4 / He主吹 / cc/min / 0） | 实体注释 |
| `string11` | He 反吹 - 检查值（视图标签：5 / He反吹 / cc/min / 0） | 实体注释 |
| `string12` | He 反吹 - 备注（视图标签：5 / He反吹 / cc/min / 0） | 实体注释 |
| `string13` | He/O2 - 检查值（视图标签：6 / He/O2 / cc/min / 0） | 实体注释 |
| `string14` | He/O2 - 备注（视图标签：6 / He/O2 / cc/min / 0） | 实体注释 |
| `string15` | He/CH4 - 检查值（视图标签：7 / He/CH4 / cc/min / 0） | 实体注释 |
| `string16` | He/CH4 - 备注（视图标签：7 / He/CH4 / cc/min / 0） | 实体注释 |
| `string17` | 解析炉 - 检查值（视图标签：8 / 解析炉 / ℃ / ＜40） | 实体注释 |
| `string18` | 解析炉 - 备注（视图标签：8 / 解析炉 / ℃ / ＜40） | 实体注释 |
| `string19` | 氧化炉 - 检查值（视图标签：9 / 氧化炉 / ℃ / 500） | 实体注释 |
| `string20` | 氧化炉 - 备注（视图标签：9 / 氧化炉 / ℃ / 500） | 实体注释 |
| `string21` | 分析状态下 /// 透射 - 检查值（视图标签：1 / 激光值 / 透射 / // / >1000） | 实体注释 |
| `string22` | 透射 - 备注（视图标签：1 / 激光值 / 透射 / // / >1000） | 实体注释 |
| `string23` | 反射 - 检查值 | 实体注释 |
| `string24` | 反射 - 备注 | 实体注释 |
| `string25` | 采样流量 - 检查值（视图标签：2 / 采样流量 / L / 0） | 实体注释 |
| `string26` | 采样流量 - 备注（视图标签：2 / 采样流量 / L / 0） | 实体注释 |
| `string27` | 腔体压力 - 检查值（视图标签：3 / 腔体压力 / kPa / 110~130） | 实体注释 |
| `string28` | 腔体压力 - 备注（视图标签：3 / 腔体压力 / kPa / 110~130） | 实体注释 |
| `string29` | He主吹 - 检查值（视图标签：4 / He主吹 / cc/min / 80/60/80 / OC阶段/EC阶段/甲烷定量阶段） | 实体注释 |
| `string30` | He 反吹 - 检查值（视图标签：5 / He反吹 / cc/min / 20/20/20 / OC阶段/EC阶段/甲烷定量阶段） | 实体注释 |
| `string31` | He/O2 - 检查值（视图标签：6 / He/O2 / cc/min / 0/20/0 / OC阶段/EC阶段/甲烷定量阶段） | 实体注释 |
| `string32` | He/CH4 - 检查值（视图标签：7 / He/CH4 / cc/min / 0/20/0 / OC阶段/EC阶段/甲烷定量阶段） | 实体注释 |
| `string33` | 解析炉 - 检查值（视图标签：8 / 解析炉 / ℃ / 800-850） | 实体注释 |
| `string34` | 解析炉 - 备注（视图标签：8 / 解析炉 / ℃ / 800-850） | 实体注释 |
| `string35` | 氧化炉 - 检查值（视图标签：9 / 氧化炉 / ℃ / 850） | 实体注释 |
| `string36` | 氧化炉 - 备注（视图标签：9 / 氧化炉 / ℃ / 850） | 实体注释 |
| `string37` | He 压力 - 检查值（视图标签：1 / He 压力 / Mpa / 大于0.2Mpa / 低于2Mpa备货） | 实体注释 |
| `string38` | He/O2 压力 - 检查值（视图标签：2 / He/O2 压力 / Mpa / 大于0.2Mpa / 低于2Mpa备货） | 实体注释 |
| `string39` | He/CH4 压力 - 检查值（视图标签：3 / He/CH4 压力 / Mpa / 大于0.2Mpa / 低于2Mpa备货） | 实体注释 |
| `string40` | 空白值TC - 检查值（视图标签：4 / 空白值TC / μg/m3 / < 0.3μg /m3） | 实体注释 |
| `string41` | 空白值TC - 备注（视图标签：4 / 空白值TC / μg/m3 / < 0.3μg /m3） | 实体注释 |
| `string42` | 10 / 实际升温程序温度偏差 / 无氧阶段 / ℃ / ±10% | cshtml 标签 |
| `string43` | 10 / 实际升温程序温度偏差 / 无氧阶段 / ℃ / ±10% | cshtml 标签 |
| `string44` | 有氧阶段 / ℃ / ±10% | cshtml 标签 |
| `string45` | 有氧阶段 / ℃ / ±10% | cshtml 标签 |
| `string46` | 内标阶段 / ℃ / ±10% | cshtml 标签 |
| `string47` | 内标阶段 / ℃ / ±10% | cshtml 标签 |
| `string48` | 5 / Denuder碳膜 | cshtml 标签 |
| `string49` | 5 / Denuder碳膜 | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_OCECMonthCheck（sup_rf_ocecmonthcheck）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECMonthCheck`、视图 `Sup_RF_OCECMonthCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bz1` | （视图标签：1 / 切割器清洁） | 实体注释 |
| `bz2` | （视图标签：2 / 泄露检查） | 实体注释 |
| `nr1` | （视图标签：1 / 切割器清洁） | 实体注释 |
| `nr2` | （视图标签：2 / 泄露检查） | 实体注释 |
| `nr3` | 3 / 溶蚀器效率 / ≥ 70% | cshtml 标签 |
| `nr4` | 4 / 仪器空白 / TC仪器空白≤ 0.3μg | cshtml 标签 |

**平台校验器：**`bz1`=required；`bz2`=required；`nr3`=required；`nr4`=required


## Sup_RF_OCECMultipointCheck（sup_rf_ocecmultipointcheck）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECMultipointCheck`、视图 `Sup_RF_OCECMultipointCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `slope` | 斜率（视图标签：旧校准常数 / 新校准常数 / 线性检查结果 / 斜率） | 实体注释 |
| `remarks` | 备注: | cshtml 标签 |
| `accuracy` | 正确度 / 相对误差% / 在±10%范围内 | cshtml 标签 |
| `intercept` | 截距 | 实体注释 |
| `precision` | 精密度 / 相对标准偏差% / ≤5% | cshtml 标签 |
| `systemblank` | 系统空白 / （μg/m³） / 应小于1.0μgC/m³ | cshtml 标签 |
| `validperiod` | 有效期（视图标签：蔗糖溶液） | 实体注释 |
| `configurator` | 配置人（视图标签：蔗糖溶液） | 实体注释 |
| `blankcarbon_1` | 空白1 - 标准碳质量（ug）（视图标签：空白1 / /） | 实体注释 |
| `blankcarbon_2` | 空白2 / / | cshtml 标签 |
| `concentration` | 标准溶液浓度（视图标签：蔗糖溶液） | 实体注释 |
| `effectivedate` | 蔗糖溶液 | cshtml 标签 |
| `factorynumber` | 上一次 / 下一次 | cshtml 标签 |
| `blankmethane_1` | 空白1 / / | cshtml 标签 |
| `blankmethane_2` | 空白2 / / | cshtml 标签 |
| `newcalibration` | 截距 | cshtml 标签 |
| `oldcalibration` | 截距 | cshtml 标签 |
| `oldcoefficient` | 旧校准常数 / 曲线斜率 / 相关系数 | cshtml 标签 |
| `instrumentmodel` | 上一次 / 下一次 | cshtml 标签 |
| `measurecarbon_1` | 测量1 - 标准碳质量（ug）（视图标签：测量1 / 10.516） | 实体注释 |
| `measurecarbon_2` | 测量2 / 10.516 | cshtml 标签 |
| `measurecarbon_3` | 测量3 / 21.03 | cshtml 标签 |
| `measurecarbon_4` | 测量4 / 21.03 | cshtml 标签 |
| `measurecarbon_5` | 测量5 / 42.065 | cshtml 标签 |
| `measurecarbon_6` | 测量6 / 42.065 | cshtml 标签 |
| `measuresixtimes` | 六次测量平均 / / / / / / | cshtml 标签 |
| `preparationdate` | 蔗糖溶液 | cshtml 标签 |
| `blanktotalarea_1` | 空白1 / / | cshtml 标签 |
| `blanktotalarea_2` | 空白2 / / | cshtml 标签 |
| `measuremethane_1` | 测量1 / 10.516 | cshtml 标签 |
| `measuremethane_2` | 测量2 / 10.516 | cshtml 标签 |
| `measuremethane_3` | 测量3 / 21.03 | cshtml 标签 |
| `measuremethane_4` | 测量4 / 21.03 | cshtml 标签 |
| `measuremethane_5` | 测量5 / 42.065 | cshtml 标签 |
| `measuremethane_6` | 测量6 / 42.065 | cshtml 标签 |
| `blankactualarea_1` | 空白1 / / | cshtml 标签 |
| `blankactualarea_2` | 空白2 / / | cshtml 标签 |
| `blankactualarea_3` | 两次空白平均 / / / / / / | cshtml 标签 |
| `blankmeaquality_1` | 空白1 / / | cshtml 标签 |
| `blankmeaquality_2` | 空白2 / / | cshtml 标签 |
| `checkdatelasttime` | 上一次 / 下一次 | cshtml 标签 |
| `measuredeviation_1` | 测量1 / 10.516 | cshtml 标签 |
| `measuredeviation_2` | 测量2 / 10.516 | cshtml 标签 |
| `measuredeviation_3` | 测量3 / 21.03 | cshtml 标签 |
| `measuredeviation_4` | 测量4 / 21.03 | cshtml 标签 |
| `measuredeviation_5` | 测量5 / 42.065 | cshtml 标签 |
| `measuredeviation_6` | 测量6 / 42.065 | cshtml 标签 |
| `measuretotalarea_1` | 测量1 / 10.516 | cshtml 标签 |
| `measuretotalarea_2` | 测量2 / 10.516 | cshtml 标签 |
| `measuretotalarea_3` | 测量3 / 21.03 | cshtml 标签 |
| `measuretotalarea_4` | 测量4 / 21.03 | cshtml 标签 |
| `measuretotalarea_5` | 测量5 / 42.065 | cshtml 标签 |
| `measuretotalarea_6` | 测量6 / 42.065 | cshtml 标签 |
| `measureactualarea_1` | 测量1 / 10.516 | cshtml 标签 |
| `measureactualarea_2` | 测量2 / 10.516 | cshtml 标签 |
| `measureactualarea_3` | 测量3 / 21.03 | cshtml 标签 |
| `measureactualarea_4` | 测量4 / 21.03 | cshtml 标签 |
| `measureactualarea_5` | 测量5 / 42.065 | cshtml 标签 |
| `measureactualarea_6` | 测量6 / 42.065 | cshtml 标签 |
| `measuremeaquality_1` | 测量1 / 10.516 | cshtml 标签 |
| `measuremeaquality_2` | 测量2 / 10.516 | cshtml 标签 |
| `measuremeaquality_3` | 测量3 / 21.03 | cshtml 标签 |
| `measuremeaquality_4` | 测量4 / 21.03 | cshtml 标签 |
| `measuremeaquality_5` | 测量5 / 42.065 | cshtml 标签 |
| `measuremeaquality_6` | 测量6 / 42.065 | cshtml 标签 |
| `newcalibrationslope` | 新校准常数 / 曲线斜率 / / / / | cshtml 标签 |
| `oldcalibrationslope` | 旧校准常数 / 曲线斜率 / 相关系数 | cshtml 标签 |
| `checkdateanothertime` | 上一次 / 下一次 | cshtml 标签 |
| `certifiedconcentration` | 认证浓度(ugC/ul)（视图标签：蔗糖溶液） | 实体注释 |
| `correlationcoefficient` | 相关系数 | 实体注释 |

**平台校验器：**`accuracy`=required；`blankactualarea_1`=required；`blankactualarea_2`=required；`blankactualarea_3`=required；`blankcarbon_1`=required；`blankcarbon_2`=required；`blankmeaquality_1`=required；`blankmeaquality_2`=required；`blankmethane_1`=required；`blankmethane_2`=required；`blanktotalarea_1`=required；`blanktotalarea_2`=required；`certifiedconcentration`=required；`concentration`=required；`configurator`=required；`correlationcoefficient`=required；`factorynumber`=required；`instrumentmodel`=required；`intercept`=required；`measureactualarea_1`=required；`measureactualarea_2`=required；`measureactualarea_3`=required；`measureactualarea_4`=required；`measureactualarea_5`=required；`measureactualarea_6`=required；`measurecarbon_1`=required；`measurecarbon_2`=required；`measurecarbon_3`=required；`measurecarbon_4`=required；`measurecarbon_5`=required；`measurecarbon_6`=required；`measuredeviation_1`=required；`measuredeviation_2`=required；`measuredeviation_3`=required；`measuredeviation_4`=required；`measuredeviation_5`=required；`measuredeviation_6`=required；`measuremeaquality_1`=required；`measuremeaquality_2`=required；`measuremeaquality_3`=required；`measuremeaquality_4`=required；`measuremeaquality_5`=required；`measuremeaquality_6`=required；`measuremethane_1`=required；`measuremethane_2`=required；`measuremethane_3`=required；`measuremethane_4`=required；`measuremethane_5`=required；`measuremethane_6`=required；`measuresixtimes`=required；`measuretotalarea_1`=required；`measuretotalarea_2`=required；`measuretotalarea_3`=required；`measuretotalarea_4`=required；`measuretotalarea_5`=required；`measuretotalarea_6`=required；`newcalibration`=required；`newcalibrationslope`=required；`oldcalibration`=required；`oldcalibrationslope`=required；`oldcoefficient`=required；`precision`=required；`slope`=required；`systemblank`=required；`validperiod`=required


## Sup_RF_OCECQuarterhCheck（sup_rf_ocecquarterhcheck）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECQuarterhCheck`、视图 `Sup_RF_OCECQuarterhCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bz1` | （视图标签：1 / Denuder碳膜更换） | 实体注释 |
| `nr1` | （视图标签：1 / Denuder碳膜更换） | 实体注释 |

**平台校验器：**`bz1`=required


## Sup_RF_OCECSamplingFlowCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECSamplingFlowCheck`、视图 `Sup_RF_OCECSamplingFlowCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 仪器资料 - 上一次核查日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time2` | 仪器资料 - 下一次核查日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time3` | 参考流量计 - 上一次计量认证时间（视图标签：截距 / 相关系数） | 实体注释 |
| `time4` | 参考流量计 - 下一次计量认证时间（视图标签：截距 / 相关系数） | 实体注释 |
| `string1` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string2` | 出厂编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string3` | 型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string4` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string5` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | 截距（视图标签：截距 / 相关系数） | 实体注释 |
| `string7` | 相关系数 | 实体注释 |
| `string8` | 仪器显示值 - 校准前 | 实体注释 |
| `string9` | 直接读取 - 校准前 | 实体注释 |
| `string10` | 已修正的标准值 - 校准前 | 实体注释 |
| `string11` | 偏差 - 校准前 | 实体注释 |
| `string12` | 校准与否（视图标签：校准前） | 实体注释 |
| `string13` | 仪器显示值 - 校准后（视图标签：校准后 / /） | 实体注释 |
| `string14` | 直接读取 - 校准后（视图标签：校准后 / /） | 实体注释 |
| `string15` | 已修正的标准值 - 校准后（视图标签：校准后 / /） | 实体注释 |
| `string16` | 偏差 - 校准后（视图标签：校准后 / /） | 实体注释 |
| `string27` | 备注： | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string2`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_OCECSingleCheck（sup_rf_ocecsinglecheck）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECSingleCheck`、视图 `Sup_RF_OCECSingleCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remarks` | 备注: | cshtml 标签 |
| `validperiod` | 有效期（视图标签：蔗糖溶液） | 实体注释 |
| `configurator` | 配置人（视图标签：蔗糖溶液） | 实体注释 |
| `concentration` | 标准溶液浓度（视图标签：蔗糖溶液） | 实体注释 |
| `effectivedate` | 蔗糖溶液 | cshtml 标签 |
| `factorynumber` | 上一次 / 下一次 | cshtml 标签 |
| `blankmethane_1` | 空白1 / 0 / / | cshtml 标签 |
| `blankmethane_2` | 空白2 / 0 / / | cshtml 标签 |
| `blankmethane_3` | 两次空白平均 / / / / | cshtml 标签 |
| `instrumentmodel` | 上一次 / 下一次 | cshtml 标签 |
| `preparationdate` | 蔗糖溶液 | cshtml 标签 |
| `blanktotalarea_1` | 空白1 / 0 / / | cshtml 标签 |
| `blanktotalarea_2` | 空白2 / 0 / / | cshtml 标签 |
| `measuremethane_1` | 测量1 | cshtml 标签 |
| `measuremethane_2` | 测量2 | cshtml 标签 |
| `measuremethane_3` | 测量3 | cshtml 标签 |
| `blankactualarea_1` | 空白1 / 0 / / | cshtml 标签 |
| `blankactualarea_2` | 空白2 / 0 / / | cshtml 标签 |
| `blankactualarea_3` | 两次空白平均 / / / / | cshtml 标签 |
| `blankmeaquality_1` | 空白1 / 0 / / | cshtml 标签 |
| `blankmeaquality_2` | 空白2 / 0 / / | cshtml 标签 |
| `checkdatelasttime` | 上一次 / 下一次 | cshtml 标签 |
| `measurestandard_1` | 测量1 | cshtml 标签 |
| `measurestandard_2` | 测量2 | cshtml 标签 |
| `measurestandard_3` | 测量3 | cshtml 标签 |
| `measuredeviation_1` | 测量1 | cshtml 标签 |
| `measuredeviation_2` | 测量2 | cshtml 标签 |
| `measuredeviation_3` | 测量3 | cshtml 标签 |
| `measuretotalarea_1` | 测量1 | cshtml 标签 |
| `measuretotalarea_2` | 测量2 | cshtml 标签 |
| `measuretotalarea_3` | 测量3 | cshtml 标签 |
| `measureactualarea_1` | 测量1 | cshtml 标签 |
| `measureactualarea_2` | 测量2 | cshtml 标签 |
| `measureactualarea_3` | 测量3 | cshtml 标签 |
| `measuremeaquality_1` | 测量1 | cshtml 标签 |
| `measuremeaquality_2` | 测量2 | cshtml 标签 |
| `measuremeaquality_3` | 测量3 | cshtml 标签 |
| `checkdateanothertime` | 上一次 / 下一次 | cshtml 标签 |
| `certifiedconcentration` | 认证浓度(ugC/ul)（视图标签：蔗糖溶液） | 实体注释 |

**平台校验器：**`blankactualarea_1`=required；`blankactualarea_2`=required；`blankactualarea_3`=required；`blankmeaquality_1`=required；`blankmeaquality_2`=required；`blankmethane_1`=required；`blankmethane_2`=required；`blankmethane_3`=required；`blanktotalarea_1`=required；`blanktotalarea_2`=required；`certifiedconcentration`=required；`concentration`=required；`configurator`=required；`factorynumber`=required；`instrumentmodel`=required；`measureactualarea_1`=required,double；`measureactualarea_2`=double；`measureactualarea_3`=double；`measuredeviation_1`=required,double；`measuredeviation_2`=double；`measuredeviation_3`=double；`measuremeaquality_1`=required,double；`measuremeaquality_2`=double；`measuremeaquality_3`=double；`measuremethane_1`=required,double；`measuremethane_2`=double；`measuremethane_3`=double；`measurestandard_1`=required,double；`measurestandard_2`=double；`measurestandard_3`=double；`measuretotalarea_1`=required,double；`measuretotalarea_2`=double；`measuretotalarea_3`=double；`validperiod`=required


## Sup_RF_OCECSunsetFlowCalibration（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECSunsetFlowCalibration`、视图 `Sup_RF_OCECSunsetFlowCalibration.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次校准日期（视图标签：截距 / 相关系数） | 实体注释 |
| `time2` | 参考流量计 - 下一次校准日期（视图标签：截距 / 相关系数） | 实体注释 |
| `time3` | OCEC分析仪资料 - 上一次校准时间（视图标签：上一次 / 下一次） | 实体注释 |
| `time4` | OCEC分析仪资料 - 下一次校准时间（视图标签：上一次 / 下一次） | 实体注释 |
| `string1` | 截距 / 相关系数 | cshtml 标签 |
| `string2` | 截距 / 相关系数 | cshtml 标签 |
| `string3` | 截距 / 相关系数 | cshtml 标签 |
| `string4` | 截距 / 相关系数 | cshtml 标签 |
| `string5` | 相关系数 | cshtml 标签 |
| `string6` | 上一次 / 下一次 | cshtml 标签 |
| `string7` | 上一次 / 下一次 | cshtml 标签 |
| `string8` | 上一次 / 下一次 | cshtml 标签 |
| `string9` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string10` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string11` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string12` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string13` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string14` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string15` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string16` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string17` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string18` | 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string19` | （视图绑定，含义见标签） | cshtml 标签 |
| `string20` | （视图绑定，含义见标签） | cshtml 标签 |
| `string21` | （视图绑定，含义见标签） | cshtml 标签 |
| `string22` | （视图绑定，含义见标签） | cshtml 标签 |
| `string23` | （视图绑定，含义见标签） | cshtml 标签 |
| `string24` | （视图绑定，含义见标签） | cshtml 标签 |
| `string25` | （视图绑定，含义见标签） | cshtml 标签 |
| `string26` | （视图绑定，含义见标签） | cshtml 标签 |
| `string27` | （视图绑定，含义见标签） | cshtml 标签 |
| `string28` | （视图绑定，含义见标签） | cshtml 标签 |
| `string29` | （视图绑定，含义见标签） | cshtml 标签 |
| `string30` | （视图绑定，含义见标签） | cshtml 标签 |
| `string31` | （视图绑定，含义见标签） | cshtml 标签 |
| `string32` | （视图绑定，含义见标签） | cshtml 标签 |
| `string33` | （视图绑定，含义见标签） | cshtml 标签 |
| `string34` | （视图绑定，含义见标签） | cshtml 标签 |
| `string35` | （视图绑定，含义见标签） | cshtml 标签 |
| `string36` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string37` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string38` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string39` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string40` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string41` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string42` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string43` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string44` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string45` | 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string46` | （视图绑定，含义见标签） | cshtml 标签 |
| `string47` | （视图绑定，含义见标签） | cshtml 标签 |
| `string48` | （视图绑定，含义见标签） | cshtml 标签 |
| `string49` | （视图绑定，含义见标签） | cshtml 标签 |
| `string50` | （视图绑定，含义见标签） | cshtml 标签 |
| `string51` | （视图绑定，含义见标签） | cshtml 标签 |
| `string52` | （视图绑定，含义见标签） | cshtml 标签 |
| `string53` | （视图绑定，含义见标签） | cshtml 标签 |
| `string54` | （视图绑定，含义见标签） | cshtml 标签 |
| `string55` | （视图绑定，含义见标签） | cshtml 标签 |
| `string56` | （视图绑定，含义见标签） | cshtml 标签 |
| `string57` | （视图绑定，含义见标签） | cshtml 标签 |
| `string58` | （视图绑定，含义见标签） | cshtml 标签 |
| `string59` | （视图绑定，含义见标签） | cshtml 标签 |
| `string60` | （视图绑定，含义见标签） | cshtml 标签 |
| `string61` | （视图绑定，含义见标签） | cshtml 标签 |
| `string62` | （视图绑定，含义见标签） | cshtml 标签 |
| `string63` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string64` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string65` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string66` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string67` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string68` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string69` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string70` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string71` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string72` | 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string73` | （视图绑定，含义见标签） | cshtml 标签 |
| `string74` | （视图绑定，含义见标签） | cshtml 标签 |
| `string75` | （视图绑定，含义见标签） | cshtml 标签 |
| `string76` | （视图绑定，含义见标签） | cshtml 标签 |
| `string77` | （视图绑定，含义见标签） | cshtml 标签 |
| `string78` | （视图绑定，含义见标签） | cshtml 标签 |
| `string79` | （视图绑定，含义见标签） | cshtml 标签 |
| `string80` | （视图绑定，含义见标签） | cshtml 标签 |
| `string81` | （视图绑定，含义见标签） | cshtml 标签 |
| `string82` | （视图绑定，含义见标签） | cshtml 标签 |
| `string83` | （视图绑定，含义见标签） | cshtml 标签 |
| `string84` | （视图绑定，含义见标签） | cshtml 标签 |
| `string85` | （视图绑定，含义见标签） | cshtml 标签 |
| `string86` | （视图绑定，含义见标签） | cshtml 标签 |
| `string87` | （视图绑定，含义见标签） | cshtml 标签 |
| `string88` | （视图绑定，含义见标签） | cshtml 标签 |
| `string89` | （视图绑定，含义见标签） | cshtml 标签 |
| `string90` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string100` | （视图绑定，含义见标签） | cshtml 标签 |
| `string101` | （视图绑定，含义见标签） | cshtml 标签 |
| `string102` | （视图绑定，含义见标签） | cshtml 标签 |
| `string103` | （视图绑定，含义见标签） | cshtml 标签 |
| `string104` | （视图绑定，含义见标签） | cshtml 标签 |
| `string105` | （视图绑定，含义见标签） | cshtml 标签 |
| `string106` | （视图绑定，含义见标签） | cshtml 标签 |
| `string107` | （视图绑定，含义见标签） | cshtml 标签 |
| `string108` | （视图绑定，含义见标签） | cshtml 标签 |
| `string109` | （视图绑定，含义见标签） | cshtml 标签 |
| `string110` | （视图绑定，含义见标签） | cshtml 标签 |
| `string111` | （视图绑定，含义见标签） | cshtml 标签 |
| `string112` | （视图绑定，含义见标签） | cshtml 标签 |
| `string113` | （视图绑定，含义见标签） | cshtml 标签 |
| `string114` | （视图绑定，含义见标签） | cshtml 标签 |
| `string115` | （视图绑定，含义见标签） | cshtml 标签 |
| `string116` | （视图绑定，含义见标签） | cshtml 标签 |
| `string117` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string118` | 设定流量 (ml/min) / 电压（V） / 参考流量计读数 (ml/min) / 参考流量计修正 (ml/min) | cshtml 标签 |
| `string119` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string120` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string121` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string122` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string123` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string124` | 参考流量计修正 (ml/min) / 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string125` | 斜率： 截距： &nbspR²： | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string100`=required；`string101`=required；`string102`=required；`string103`=required；`string104`=required；`string105`=required；`string106`=required；`string107`=required；`string108`=required；`string109`=required；`string11`=required；`string110`=required；`string111`=required；`string112`=required；`string113`=required；`string114`=required；`string115`=required；`string116`=required；`string117`=required；`string118`=required；`string119`=required；`string12`=required；`string120`=required；`string121`=required；`string122`=required；`string123`=required；`string124`=required；`string125`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string4`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string46`=required；`string47`=required；`string48`=required；`string49`=required；`string5`=required；`string50`=required；`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required；`string56`=required；`string57`=required；`string58`=required；`string59`=required；`string6`=required；`string60`=required；`string61`=required；`string62`=required；`string63`=required；`string64`=required；`string65`=required；`string66`=required；`string67`=required；`string68`=required；`string69`=required；`string7`=required；`string70`=required；`string71`=required；`string72`=required；`string73`=required；`string74`=required；`string75`=required；`string76`=required；`string77`=required；`string78`=required；`string79`=required；`string8`=required；`string80`=required；`string81`=required；`string82`=required；`string83`=required；`string84`=required；`string85`=required；`string86`=required；`string87`=required；`string88`=required；`string89`=required；`string9`=required；`string90`=required


## Sup_RF_OCECWeekCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECWeekCheck`、视图 `Sup_RF_OCECWeekCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `snsd` | （视图标签：室内温度 / 室内湿度） | 实体注释 |
| `snwd` | （视图标签：室内温度 / 室内湿度） | 实体注释 |
| `zfsd` | （视图标签：站房温度 / 站房湿度） | 实体注释 |
| `zfwd` | （视图标签：站房温度 / 站房湿度） | 实体注释 |
| `tb1bz1` | （视图标签：1 / 仪器状态） | 实体注释 |
| `tb1bz2` | （视图标签：2 / Idle状态下载气流量稳定性 （±1cc/min）） | 实体注释 |
| `tb1bz3` | （视图标签：3 / 载气流量零点 （±1cc/min）） | 实体注释 |
| `tb1bz4` | （视图标签：4 / 采样流量稳定性 （8L/min，±5%）） | 实体注释 |
| `tb1bz5` | （视图标签：5 / 石英滤膜） | 实体注释 |
| `tb1bz6` | （视图标签：7 / 激光修正值 （0.88-1.00）） | 实体注释 |
| `tb1bz7` | （视图标签：8 / 后炉温度 （分析期间，500-870℃）） | 实体注释 |
| `tb1bz8` | （视图标签：9 / 前炉温度 （分析期间，500-870℃）） | 实体注释 |
| `tb1bz9` | （视图标签：11 / 空白值检查 （±0.3ugC）） | 实体注释 |
| `tb1nr1` | （视图标签：1 / 仪器状态） | 实体注释 |
| `tb1nr2` | （视图标签：2 / Idle状态下载气流量稳定性 （±1cc/min）） | 实体注释 |
| `tb1nr3` | （视图标签：3 / 载气流量零点 （±1cc/min）） | 实体注释 |
| `tb1nr4` | （视图标签：4 / 采样流量稳定性 （8L/min，±5%）） | 实体注释 |
| `tb1nr5` | （视图标签：5 / 石英滤膜） | 实体注释 |
| `tb1nr6` | （视图标签：7 / 激光修正值 （0.88-1.00）） | 实体注释 |
| `tb1nr7` | （视图标签：8 / 后炉温度 （分析期间，500-870℃）） | 实体注释 |
| `tb1nr8` | （视图标签：9 / 前炉温度 （分析期间，500-870℃）） | 实体注释 |
| `tb1nr9` | （视图标签：11 / 空白值检查 （±0.3ugC）） | 实体注释 |
| `tb2dy1` | （视图标签：14 / He钢瓶气 / 有效期） | 实体注释 |
| `tb2dy2` | （视图标签：15 / He/O2钢瓶气 / 有效期） | 实体注释 |
| `tb2dy3` | （视图标签：16 / He/CH4钢瓶气 / 有效期） | 实体注释 |
| `tb2gy1` | （视图标签：14 / He钢瓶气 / 有效期） | 实体注释 |
| `tb2gy2` | （视图标签：15 / He/O2钢瓶气 / 有效期） | 实体注释 |
| `tb2gy3` | （视图标签：16 / He/CH4钢瓶气 / 有效期） | 实体注释 |
| `tb1bz10` | （视图标签：12 / Oven压力 （Idle状态，0-2.75psi）） | 实体注释 |
| `tb1bz11` | （视图标签：13 / Oven压力 （Sample状态，±2.75psi）） | 实体注释 |
| `tb1bz12` | （视图标签：6 / Denuder碳膜） | 实体注释 |
| `tb1nr10` | （视图标签：12 / Oven压力 （Idle状态，0-2.75psi）） | 实体注释 |
| `tb1nr11` | （视图标签：13 / Oven压力 （Sample状态，±2.75psi）） | 实体注释 |
| `tb1nr12` | （视图标签：6 / Denuder碳膜） | 实体注释 |
| `tb1nr13` | 无氧阶段 / 在±10%范围内 | cshtml 标签 |
| `tb1nr14` | 无氧阶段 / 在±10%范围内 | cshtml 标签 |
| `tb1nr15` | 无氧阶段 / 在±10%范围内 | cshtml 标签 |
| `tb1nr16` | 有氧阶段 / 在±10%范围内 | cshtml 标签 |
| `tb1nr17` | 有氧阶段 / 在±10%范围内 | cshtml 标签 |
| `tb1nr18` | 有氧阶段 / 在±10%范围内 | cshtml 标签 |
| `tb1nr19` | 内标阶段 / 在±10%范围内 | cshtml 标签 |
| `tb1nr20` | 内标阶段 / 在±10%范围内 | cshtml 标签 |
| `tb1nr21` | 内标阶段 / 在±10%范围内 | cshtml 标签 |
| `tb2yxq1` | （视图标签：14 / He钢瓶气 / 有效期） | 实体注释 |
| `tb2yxq2` | （视图标签：15 / He/O2钢瓶气 / 有效期） | 实体注释 |
| `tb2yxq3` | （视图标签：16 / He/CH4钢瓶气 / 有效期） | 实体注释 |

**平台校验器：**`snsd`=required；`snwd`=required；`tb1bz1`=required；`tb1bz10`=required；`tb1bz11`=required；`tb1bz12`=required；`tb1bz2`=required；`tb1bz3`=required；`tb1bz4`=required；`tb1bz5`=required；`tb1bz6`=required；`tb1bz7`=required；`tb1bz8`=required；`tb1bz9`=required；`tb1nr10`=required；`tb1nr11`=required；`tb1nr13`=required；`tb1nr14`=required；`tb1nr15`=required；`tb1nr16`=required；`tb1nr17`=required；`tb1nr18`=required；`tb1nr19`=required；`tb1nr20`=required；`tb1nr21`=required；`tb1nr6`=required；`tb1nr7`=required；`tb1nr8`=required；`tb1nr9`=required；`tb2dy1`=required；`tb2dy2`=required；`tb2dy3`=required；`tb2gy1`=required；`tb2gy2`=required；`tb2gy3`=required；`zfsd`=required；`zfwd`=required


## Sup_RF_OCECYearCheck（sup_rf_ocecyearcheck）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OCECYearCheck`、视图 `Sup_RF_OCECYearCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bz1` | （视图标签：1 / 采样泵维护与检查） | 实体注释 |
| `bz2` | （视图标签：2 / 激光维护与检查） | 实体注释 |
| `bz3` | （视图标签：3 / 电磁阀维护与检查） | 实体注释 |
| `bz4` | （视图标签：4 / 气路维护与检查） | 实体注释 |
| `bz5` | （视图标签：5 / 石英炉维护与检查） | 实体注释 |
| `bz6` | （视图标签：6 / NDIR维护与检查） | 实体注释 |
| `nr1` | （视图标签：1 / 采样泵维护与检查） | 实体注释 |
| `nr2` | （视图标签：2 / 激光维护与检查） | 实体注释 |
| `nr3` | （视图标签：3 / 电磁阀维护与检查） | 实体注释 |
| `nr4` | （视图标签：4 / 气路维护与检查） | 实体注释 |
| `nr5` | （视图标签：5 / 石英炉维护与检查） | 实体注释 |
| `nr6` | （视图标签：6 / NDIR维护与检查） | 实体注释 |

**平台校验器：**`bz1`=required；`bz2`=required；`bz3`=required；`bz4`=required；`bz5`=required；`bz6`=required


## Sup_RF_OcecEnvironmentCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OcecEnvironmentCheck`、视图 `Sup_RF_OcecEnvironmentCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 校准日期（视图标签：OCEC） | 实体注释 |
| `time2` | 校准日期（视图标签：OCEC） | 实体注释 |
| `time3` | 设备型号 | 实体注释 |
| `time4` | 下次校准日期（视图标签：设备型号 / 下次校准日期） | 实体注释 |
| `time5` | 上次校准日期 | 实体注释 |
| `time6` | 下次校准日期 | 实体注释 |
| `time7` | 上次校准日期（视图标签：测量范围 / 上次校准日期） | 实体注释 |
| `string1` | 仪器型号（视图标签：OCEC） | 实体注释 |
| `string2` | 出厂编号（视图标签：OCEC） | 实体注释 |
| `string3` | 参考温度计资料 设备型号（视图标签：设备型号 / 出厂编号） | 实体注释 |
| `string4` | 参考温度计资料 出厂编号（视图标签：设备型号 / 出厂编号） | 实体注释 |
| `string5` | 仪器序列号（视图标签：测量范围 / 上次校准日期） | 实体注释 |
| `string6` | 测量范围 | 实体注释 |
| `string7` | 直接读取的标准读数（视图标签：校准前 / 校准后） | 实体注释 |
| `string8` | 已修正的标准值（视图标签：校准前 / 校准后） | 实体注释 |
| `string9` | 校准前（视图标签：校准前 / 校准后） | 实体注释 |
| `string10` | 校准后（视图标签：校准前 / 校准后） | 实体注释 |
| `string11` | 设备型号（视图标签：设备型号 ℃ / 校准方程(Y_真实值，X_显示值)） | 实体注释 |
| `string12` | 出厂编号（视图标签：出厂编号 / 斜率 / 截距 / 相关系数） | 实体注释 |
| `string13` | 斜率（视图标签：上次校准日期） | 实体注释 |
| `string14` | 截距（视图标签：上次校准日期） | 实体注释 |
| `string15` | 相关系数（视图标签：上次校准日期） | 实体注释 |
| `string16` | （视图标签：下次校准日期） | 实体注释 |
| `string17` | 直接读取的标准读数（视图标签：校准前 / 校准后 *） | 实体注释 |
| `string18` | 已修正的标准值（视图标签：校准前 / 校准后 *） | 实体注释 |
| `string19` | 校准前（视图标签：校准前 / 校准后 *） | 实体注释 |
| `string20` | 校准后（视图标签：校准前 / 校准后 *） | 实体注释 |
| `string21` | 设备型号（视图标签：设备型号 / 下次校准日期） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string3`=required；`string4`=required；`string5`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_OcecFlowVerificationCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OcecFlowVerificationCheck`、视图 `Sup_RF_OcecFlowVerificationCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time2` | 校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time3` | 计量认证时间 1（视图标签：截距 / 相关系数） | 实体注释 |
| `time4` | 计量认证时间 2（视图标签：截距 / 相关系数） | 实体注释 |
| `time5` | 上次校准日期 | 实体注释 |
| `time6` | 下次校准日期 | 实体注释 |
| `time7` | 上次校准日期 | 实体注释 |
| `string1` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string2` | 出厂编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string3` | 型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string4` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string5` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | 拮据（视图标签：截距 / 相关系数） | 实体注释 |
| `string7` | 相关系数（视图标签：截距 / 相关系数） | 实体注释 |
| `string8` | 仪器显示值（视图标签：校准前） | 实体注释 |
| `string9` | 直接读取（视图标签：校准前） | 实体注释 |
| `string10` | 已修正的标准值（视图标签：校准前） | 实体注释 |
| `string11` | 偏差（视图标签：校准前） | 实体注释 |
| `string12` | 校准与否（视图标签：校准前） | 实体注释 |
| `string13` | 仪器显示值（视图标签：校准后） | 实体注释 |
| `string14` | 直接读取（视图标签：校准后） | 实体注释 |
| `string15` | 已修正的标准值（视图标签：校准后） | 实体注释 |
| `string16` | 偏差（视图标签：校准后） | 实体注释 |
| `string17` | 校准与否（视图标签：校准后） | 实体注释 |
| `string18` | 氯甲烷通道 - 校准前 - 仪器显示值 | 实体注释 |
| `string19` | 氯甲烷通道 - 校准前 - 直接读取 | 实体注释 |
| `string20` | 氯甲烷通道 - 校准前 - 已修正的标准值 | 实体注释 |
| `string21` | 氯甲烷通道 - 校准前 - 偏差 | 实体注释 |
| `string22` | 氯甲烷通道 - 校准前 - 校准与否 | 实体注释 |
| `string23` | 氯甲烷通道 - 校准后 - 仪器显示值 | 实体注释 |
| `string24` | 氯甲烷通道 - 校准后 - 直接读取 | 实体注释 |
| `string25` | 氯甲烷通道 - 校准后 - 已修正的标准值 | 实体注释 |
| `string26` | 氯甲烷通道 - 校准后 - 偏差 | 实体注释 |
| `string27` | 氯甲烷通道 - 校准后 - 校准与否 | 实体注释 |
| `string28` | 氢氧通道 - 校准前 - 仪器显示值 | 实体注释 |
| `string29` | 氢氧通道 - 校准前 - 直接读取 | 实体注释 |
| `string30` | 氢氧通道 - 校准前 - 已修正的标准值 | 实体注释 |
| `string31` | 氢氧通道 - 校准前 - 偏差 | 实体注释 |
| `string32` | 氢氧通道 - 校准前 - 校准与否 | 实体注释 |
| `string33` | 氢氧通道 - 校准后 - 仪器显示值 | 实体注释 |
| `string34` | 氢氧通道 - 校准后 - 直接读取 | 实体注释 |
| `string35` | 氢氧通道 - 校准后 - 已修正的标准值 | 实体注释 |
| `string36` | 氢氧通道 - 校准后 - 偏差 | 实体注释 |
| `string37` | 氢氧通道 - 校准后 - 校准与否 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_OcecHeliumMethaneCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OcecHeliumMethaneCheck`、视图 `Sup_RF_OcecHeliumMethaneCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 计量认证时间 上一次（视图标签：截距 / 相关系数） | 实体注释 |
| `time2` | 计量认证时间 下一次（视图标签：截距 / 相关系数） | 实体注释 |
| `time3` | OCEC分析仪资料 校准日期 上一次（视图标签：上一次 / 上一次） | 实体注释 |
| `time4` | OCEC分析仪资料 校准日期 下一次（视图标签：上一次 / 上一次） | 实体注释 |
| `time5` |  | 实体注释 |
| `time6` |  | 实体注释 |
| `time7` |  | 实体注释 |
| `string1` | 参考流量计 型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string2` | 参考流量计-出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string3` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string4` | 截距（视图标签：截距 / 相关系数） | 实体注释 |
| `string5` | 相关系数（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | OCEC分析仪资料 -仪器型号（视图标签：上一次 / 上一次） | 实体注释 |
| `string7` | OCEC分析仪资料-出厂编号（视图标签：上一次 / 上一次） | 实体注释 |
| `string8` | OCEC分析仪资料 -监测项目（视图标签：上一次 / 上一次） | 实体注释 |
| `string9` | 项目（视图标签：误差 % / 检查结果） | 实体注释 |
| `string10` | 设定流量（视图标签：误差 % / 检查结果） | 实体注释 |
| `string11` | 显示流量（视图标签：误差 % / 检查结果） | 实体注释 |
| `string12` | 参考流量计读数（视图标签：误差 % / 检查结果） | 实体注释 |
| `string13` | 参考流量计修正（视图标签：误差 % / 检查结果） | 实体注释 |
| `string14` | 误差（视图标签：误差 % / 检查结果） | 实体注释 |
| `string15` | 检查结果（视图标签：误差 % / 检查结果） | 实体注释 |
| `string16` | （视图标签：校准前） | 实体注释 |
| `string17` | 校准前 | cshtml 标签 |
| `string18` | 校准前 | cshtml 标签 |
| `string19` | 校准前 | cshtml 标签 |
| `string20` | 校准前 | cshtml 标签 |
| `string21` | 校准后 | cshtml 标签 |
| `string22` | 校准后 | cshtml 标签 |
| `string23` | 校准后 | cshtml 标签 |
| `string24` | 校准后 | cshtml 标签 |
| `string25` | 校准后 | cshtml 标签 |
| `string26` | 校准前 | cshtml 标签 |
| `string27` | 校准前 | cshtml 标签 |
| `string28` | 校准前 | cshtml 标签 |
| `string29` | 校准前 | cshtml 标签 |
| `string30` | 校准前 | cshtml 标签 |
| `string31` | 校准后 | cshtml 标签 |
| `string32` | 校准后 | cshtml 标签 |
| `string33` | 校准后 | cshtml 标签 |
| `string34` | 校准后 | cshtml 标签 |
| `string35` | 校准后 | cshtml 标签 |
| `string36` | 校准前 | cshtml 标签 |
| `string37` | 校准前 | cshtml 标签 |
| `string38` | 校准前 | cshtml 标签 |
| `string39` | 校准前 | cshtml 标签 |
| `string40` | 校准前 | cshtml 标签 |
| `string41` | 校准后 | cshtml 标签 |
| `string42` | 校准后 | cshtml 标签 |
| `string43` | 校准后 | cshtml 标签 |
| `string44` | 校准后 | cshtml 标签 |
| `string45` | 校准后 | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string4`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_OcecOrganicCarbonCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/OCEC.docx
- 源码依据：实体 `Sup_RF_OcecOrganicCarbonCheck`、视图 `Sup_RF_OcecOrganicCarbonCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time2` | 校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time3` | 计量认证时间 1（视图标签：截距 / 相关系数） | 实体注释 |
| `time4` | 计量认证时间 2（视图标签：截距 / 相关系数） | 实体注释 |
| `time5` | 上次校准日期 | 实体注释 |
| `time6` | 下次校准日期 | 实体注释 |
| `time7` | 上次校准日期 | 实体注释 |
| `string1` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string2` | 出厂编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string3` | 型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string4` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string5` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | 拮据（视图标签：截距 / 相关系数） | 实体注释 |
| `string7` | 相关系数（视图标签：截距 / 相关系数） | 实体注释 |
| `string8` | 仪器显示值（视图标签：校准前） | 实体注释 |
| `string9` | 直接读取（视图标签：校准前） | 实体注释 |
| `string10` | 已修正的标准值（视图标签：校准前） | 实体注释 |
| `string11` | 偏差（视图标签：校准前） | 实体注释 |
| `string12` | 校准与否（视图标签：校准前） | 实体注释 |
| `string13` | 仪器显示值（视图标签：校准后） | 实体注释 |
| `string14` | 直接读取（视图标签：校准后） | 实体注释 |
| `string15` | 已修正的标准值（视图标签：校准后） | 实体注释 |
| `string16` | 偏差（视图标签：校准后） | 实体注释 |
| `string17` | 校准与否（视图标签：校准后） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string2`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_PANsFlowCheck（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/PANs.docx
- 源码依据：实体 `Sup_RF_PANsFlowCheck`、视图 `Sup_RF_PANsFlowCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 高量程流量计检定日期（视图标签：流量计型号 (高量程） / 流量计编号 / 检定日期） | 实体注释 |
| `time2` | 低量程流量计检定日期（视图标签：流量计型号 (低量程） / 流量计编号 / 检定日期） | 实体注释 |
| `time3` | 温度计检定日期（视图标签：温度计型号 / 温度计编号 / 检定日期） | 实体注释 |
| `time4` | 气压计检定日期（视图标签：气压计型号 / 气压计编号 / 检定日期） | 实体注释 |
| `string1` | 校准仪型号（视图标签：校准仪型号 / 校准仪编号） | 实体注释 |
| `string2` | 校准仪编号（视图标签：校准仪型号 / 校准仪编号） | 实体注释 |
| `string3` | 流量计型号(高量程）（视图标签：流量计型号 (高量程） / 流量计编号 / 检定日期） | 实体注释 |
| `string4` | 流量计编号(高量程）（视图标签：流量计型号 (高量程） / 流量计编号 / 检定日期） | 实体注释 |
| `string5` | 流量计型号(低量程）（视图标签：流量计型号 (低量程） / 流量计编号 / 检定日期） | 实体注释 |
| `string6` | 流量计编号(低量程）（视图标签：流量计型号 (低量程） / 流量计编号 / 检定日期） | 实体注释 |
| `string7` | 温度计型号（视图标签：温度计型号 / 温度计编号 / 检定日期） | 实体注释 |
| `string8` | 温度计编号（视图标签：温度计型号 / 温度计编号 / 检定日期） | 实体注释 |
| `string9` | 气压计型号（视图标签：气压计型号 / 气压计编号 / 检定日期） | 实体注释 |
| `string10` | 气压计编号（视图标签：气压计型号 / 气压计编号 / 检定日期） | 实体注释 |
| `string11` | 环境气压kPa（视图标签：环境气压kPa / 环境温度℃） | 实体注释 |
| `string12` | 环境温度℃（视图标签：环境气压kPa / 环境温度℃） | 实体注释 |
| `string13` | 零气流量控制器 仪器读数（视图标签：1 / 975.79mL/min） | 实体注释 |
| `string14` | 零气流量控制器 流量计读数（视图标签：1 / 975.79mL/min） | 实体注释 |
| `string15` | 零气流量控制器 流量计修正到标况下读数（视图标签：1 / 975.79mL/min） | 实体注释 |
| `string16` | 零气流量控制器 误差（视图标签：1 / 975.79mL/min） | 实体注释 |
| `string17` | NO标气流量控制器 仪器读数（视图标签：2 / 4.21ml/min） | 实体注释 |
| `string18` | NO标气流量控制器 流量计读数（视图标签：2 / 4.21ml/min） | 实体注释 |
| `string19` | NO标气流量控制器 流量计修正到标况下读数（视图标签：2 / 4.21ml/min） | 实体注释 |
| `string20` | NO标气流量控制器 误差（视图标签：2 / 4.21ml/min） | 实体注释 |
| `string21` | 丙酮标气流量控制器 仪器读数（视图标签：3 / 20ml/min） | 实体注释 |
| `string22` | 丙酮标气流量控制器 流量计读数（视图标签：3 / 20ml/min） | 实体注释 |
| `string23` | 丙酮标气流量控制器 流量计修正到标况下读数（视图标签：3 / 20ml/min） | 实体注释 |
| `string24` | 丙酮标气流量控制器 误差（视图标签：3 / 20ml/min） | 实体注释 |
| `string25` | 系统残留(ppb) | cshtml 标签 |
| `string43` | 曲线方程 | 实体注释 |
| `string44` | 线性相关系数 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_PANsRepeatabilityCheck（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/PANs.docx
- 源码依据：实体 `Sup_RF_PANsRepeatabilityCheck`、视图 `Sup_RF_PANsRepeatabilityCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `string1` | 仪器型号（视图标签：仪器信息 / 仪器型号 / 仪器编号） | 实体注释 |
| `string2` | 仪器编号（视图标签：仪器信息 / 仪器型号 / 仪器编号） | 实体注释 |
| `string3` | 校准仪型号（视图标签：校准仪信息 / 校准仪型号 / 校准仪编号） | 实体注释 |
| `string4` | 校准仪编号（视图标签：校准仪信息 / 校准仪型号 / 校准仪编号） | 实体注释 |
| `string5` | 目标值（ppb） | 实体注释 |
| `string6` | 记录值1（视图标签：记录值6 / 记录值7） | 实体注释 |
| `string7` | 记录值2（视图标签：记录值6 / 记录值7） | 实体注释 |
| `string8` | 记录值3（视图标签：记录值6 / 记录值7） | 实体注释 |
| `string9` | 记录值4（视图标签：记录值6 / 记录值7） | 实体注释 |
| `string10` | 记录值5（视图标签：记录值6 / 记录值7） | 实体注释 |
| `string11` | 记录值6（视图标签：记录值6 / 记录值7） | 实体注释 |
| `string12` | 记录值7（视图标签：记录值6 / 记录值7） | 实体注释 |
| `string13` | 平均值 | 实体注释 |
| `string14` | 标准偏差SD | 实体注释 |
| `string15` | 相对标准偏差RSD（视图标签：相对标准偏差RSD（要求：≤3%）） | 实体注释 |
| `string43` | 曲线方程 | 实体注释 |
| `string44` | 线性相关系数 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_PANsStabilityCheck（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/PANs.docx
- 源码依据：实体 `Sup_RF_PANsStabilityCheck`、视图 `Sup_RF_PANsStabilityCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 记录日期1 | 实体注释 |
| `time2` | 记录日期2 | 实体注释 |
| `string1` | 仪器型号（视图标签：仪器信息 / 仪器型号 / 仪器编号） | 实体注释 |
| `string2` | 仪器编号（视图标签：仪器信息 / 仪器型号 / 仪器编号） | 实体注释 |
| `string3` | 校准仪型号（视图标签：校准仪信息 / 校准仪型号 / 校准仪编号） | 实体注释 |
| `string4` | 校准仪编号（视图标签：校准仪信息 / 校准仪型号 / 校准仪编号） | 实体注释 |
| `string5` | 目标值（ppb） | 实体注释 |
| `string6` | 记录值1 | 实体注释 |
| `string7` | 记录值1 | 实体注释 |
| `string8` | 记录值2 | 实体注释 |
| `string9` | 记录值2 | 实体注释 |
| `string10` | 记录值3 | 实体注释 |
| `string11` | 记录值3 | 实体注释 |
| `string12` | 记录值4 | 实体注释 |
| `string13` | 记录值4 | 实体注释 |
| `string14` | 记录值5 | 实体注释 |
| `string15` | 记录值5 | 实体注释 |
| `string16` | 记录值6 | 实体注释 |
| `string17` | 记录值6 | 实体注释 |
| `string18` | 记录值7 | 实体注释 |
| `string19` | 记录值7 | 实体注释 |
| `string20` | 平均值 | 实体注释 |
| `string21` | 平均值 | 实体注释 |
| `string22` | 测试结果（视图标签：测试结果 （要求：≤5%）） | 实体注释 |
| `string43` | 曲线方程 | 实体注释 |
| `string44` | 线性相关系数 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_PANsWeekCheck（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/PANs.docx
- 源码依据：实体 `Sup_RF_PANsWeekCheck`、视图 `Sup_RF_PANsWeekCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | N2有效期（视图标签：气瓶信息 / N2气瓶编号 / N2有效期 / N2瓶内压力） | 实体注释 |
| `time2` | He有效期（视图标签：He气瓶编号 / He有效期 / He瓶内压力） | 实体注释 |
| `time3` | 丙酮有效期（视图标签：丙酮气瓶编号 / 丙酮有效期 / 丙酮瓶内压力） | 实体注释 |
| `time4` | NO有效期（视图标签：NO气瓶编号 / NO有效期 / NO瓶内压力） | 实体注释 |
| `time5` | 校准日期（视图标签：线性相关系数R2≥0.995 / 校准日期） | 实体注释 |
| `bool_1` | 响应值 / 零点标定ppb / 是否合格 | cshtml 标签 |
| `string1` | 仪器型号（视图标签：仪器信息 / 仪器型号 / 仪器编号） | 实体注释 |
| `string2` | 仪器编号（视图标签：仪器信息 / 仪器型号 / 仪器编号） | 实体注释 |
| `string3` | 校准仪信息（视图标签：校准仪信息 / 校准仪型号 / 校准仪编号） | 实体注释 |
| `string4` | 校准仪编号（视图标签：校准仪信息 / 校准仪型号 / 校准仪编号） | 实体注释 |
| `string5` | N2气瓶编号（视图标签：气瓶信息 / N2气瓶编号 / N2有效期 / N2瓶内压力） | 实体注释 |
| `string6` | N2瓶内压力（视图标签：气瓶信息 / N2气瓶编号 / N2有效期 / N2瓶内压力） | 实体注释 |
| `string7` | He气瓶编号（视图标签：He气瓶编号 / He有效期 / He瓶内压力） | 实体注释 |
| `string8` | He瓶内压力（视图标签：He气瓶编号 / He有效期 / He瓶内压力） | 实体注释 |
| `string9` | 丙酮气瓶编号（视图标签：丙酮气瓶编号 / 丙酮有效期 / 丙酮瓶内压力） | 实体注释 |
| `string10` | 丙酮瓶内压力（视图标签：丙酮气瓶编号 / 丙酮有效期 / 丙酮瓶内压力） | 实体注释 |
| `string11` | NO气瓶编号（视图标签：NO气瓶编号 / NO有效期 / NO瓶内压力） | 实体注释 |
| `string12` | NO瓶内压力（视图标签：NO气瓶编号 / NO有效期 / NO瓶内压力） | 实体注释 |
| `string13` | 单点标定ppb（视图标签：单点标定ppb / 校准前 / 校准后） | 实体注释 |
| `string14` | 校准前（视图标签：单点标定ppb / 校准前 / 校准后） | 实体注释 |
| `string15` | 校准后（视图标签：单点标定ppb / 校准前 / 校准后） | 实体注释 |
| `string16` | 偏差<10％（视图标签：偏差<10％ / 偏差<10％） | 实体注释 |
| `string17` | 偏差<10％（视图标签：偏差<10％ / 偏差<10％） | 实体注释 |
| `string18` | 曲线方程（视图标签：校准曲线更新 / 曲线方程） | 实体注释 |
| `string19` | 线性相关系数R2≥0.995（视图标签：线性相关系数R2≥0.995 / 校准日期） | 实体注释 |
| `string20` | TEC柱箱温度 / ℃ / 11.5～12.5 | cshtml 标签 |
| `string21` | TEC柱箱温度 / ℃ / 11.5～12.5 | cshtml 标签 |
| `string22` | ECD温度 / ℃ / 49～51 | cshtml 标签 |
| `string23` | ECD温度 / ℃ / 49～51 | cshtml 标签 |
| `string24` | 柱前压 / kPa / 17.5～18.5 | cshtml 标签 |
| `string25` | 柱前压 / kPa / 17.5～18.5 | cshtml 标签 |
| `string26` | 尾吹流量 / mL/min / 24～26 | cshtml 标签 |
| `string27` | 尾吹流量 / mL/min / 24～26 | cshtml 标签 |
| `string28` | 汞灯温度 / ℃ / 35～45 | cshtml 标签 |
| `string29` | 汞灯温度 / ℃ / 35～45 | cshtml 标签 |
| `string30` | 采样管路是否干净 / - / - | cshtml 标签 |
| `string31` | 采样管路是否干净 / - / - | cshtml 标签 |
| `string32` | 采样管路是否有冷凝水 / - / - | cshtml 标签 |
| `string33` | 采样管路是否有冷凝水 / - / - | cshtml 标签 |
| `string34` | 采样总管风机是否正常工作 / - / - | cshtml 标签 |
| `string35` | 采样总管风机是否正常工作 / - / - | cshtml 标签 |
| `string36` | 滤膜是否更换 / - / - | cshtml 标签 |
| `string37` | 滤膜是否更换 / - / - | cshtml 标签 |
| `string38` | 检查/更换硅胶 / - / - | cshtml 标签 |
| `string39` | 检查/更换硅胶 / - / - | cshtml 标签 |
| `string40` | 积分参数是否调整 / - / - | cshtml 标签 |
| `string41` | 积分参数是否调整 / - / - | cshtml 标签 |
| `string42` | 响应值 / 零点标定ppb / 是否合格 | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string13`=required,double；`string14`=required,double；`string15`=required,double；`string16`=required,double；`string17`=required,double；`string19`=required,double；`string42`=required,double


## Sup_RF_PANsWorkCurveCalibration（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/PANs.docx
- 源码依据：实体 `Sup_RF_PANsWorkCurveCalibration`、视图 `Sup_RF_PANsWorkCurveCalibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | N2有效期（视图标签：气瓶信息 / N2气瓶编号 / N2有效期 / N2瓶内压力） | 实体注释 |
| `time2` | He有效期（视图标签：He气瓶编号 / He有效期 / He瓶内压力） | 实体注释 |
| `time3` | 丙酮有效期（视图标签：丙酮气瓶编号 / 丙酮有效期 / 丙酮瓶内压力） | 实体注释 |
| `time4` | NO有效期（视图标签：NO气瓶编号 / NO有效期 / NO瓶内压力） | 实体注释 |
| `time5` | 校准日期（视图标签：线性相关系数R2≥0.995 / 校准日期） | 实体注释 |
| `string1` | 仪器型号（视图标签：仪器信息 / 仪器型号 / 仪器编号） | 实体注释 |
| `string2` | 仪器编号（视图标签：仪器信息 / 仪器型号 / 仪器编号） | 实体注释 |
| `string3` | 校准仪信息（视图标签：校准仪信息 / 校准仪型号 / 校准仪编号） | 实体注释 |
| `string4` | 校准仪编号（视图标签：校准仪信息 / 校准仪型号 / 校准仪编号） | 实体注释 |
| `string5` | N2气瓶编号（视图标签：气瓶信息 / N2气瓶编号 / N2有效期 / N2瓶内压力） | 实体注释 |
| `string6` | N2瓶内压力（视图标签：气瓶信息 / N2气瓶编号 / N2有效期 / N2瓶内压力） | 实体注释 |
| `string7` | He气瓶编号（视图标签：He气瓶编号 / He有效期 / He瓶内压力） | 实体注释 |
| `string8` | He瓶内压力（视图标签：He气瓶编号 / He有效期 / He瓶内压力） | 实体注释 |
| `string9` | 丙酮气瓶编号（视图标签：丙酮气瓶编号 / 丙酮有效期 / 丙酮瓶内压力） | 实体注释 |
| `string10` | 丙酮瓶内压力（视图标签：丙酮气瓶编号 / 丙酮有效期 / 丙酮瓶内压力） | 实体注释 |
| `string11` | NO气瓶编号（视图标签：NO气瓶编号 / NO有效期 / NO瓶内压力） | 实体注释 |
| `string12` | NO瓶内压力（视图标签：NO气瓶编号 / NO有效期 / NO瓶内压力） | 实体注释 |
| `string13` | 5 | cshtml 标签 |
| `string14` | 5 | cshtml 标签 |
| `string15` | 5 | cshtml 标签 |
| `string16` | 5 | cshtml 标签 |
| `string17` | 5 | cshtml 标签 |
| `string18` | 5 | cshtml 标签 |
| `string19` | 4 | cshtml 标签 |
| `string20` | 4 | cshtml 标签 |
| `string21` | 4 | cshtml 标签 |
| `string22` | 4 | cshtml 标签 |
| `string23` | 4 | cshtml 标签 |
| `string24` | 4 | cshtml 标签 |
| `string25` | 3 | cshtml 标签 |
| `string26` | 3 | cshtml 标签 |
| `string27` | 3 | cshtml 标签 |
| `string28` | 3 | cshtml 标签 |
| `string29` | 3 | cshtml 标签 |
| `string30` | 3 | cshtml 标签 |
| `string31` | 2 | cshtml 标签 |
| `string32` | 2 | cshtml 标签 |
| `string33` | 2 | cshtml 标签 |
| `string34` | 2 | cshtml 标签 |
| `string35` | 2 | cshtml 标签 |
| `string36` | 2 | cshtml 标签 |
| `string37` | 1 | cshtml 标签 |
| `string38` | 1 | cshtml 标签 |
| `string39` | 1 | cshtml 标签 |
| `string40` | 1 | cshtml 标签 |
| `string41` | 1 | cshtml 标签 |
| `string42` | 1 | cshtml 标签 |
| `string43` | 曲线方程（视图标签：校准曲线更新 / 曲线方程） | 实体注释 |
| `string44` | 线性相关系数（视图标签：线性相关系数R2≥0.995 / 校准日期） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_PDLIYearCheck（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/臭氧激光雷达.docx + 颗粒物组分/颗粒物激光雷达.docx
- 源码依据：实体 `Sup_RF_PDLIYearCheck`、视图 `Sup_RF_PDLIYearCheck.cshtml`、Vue 移植版 x12

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：送检时间） | 实体注释 |
| `time2` | 结束时间（视图标签：送检时间） | 实体注释 |


## Sup_RF_PM1MonitorInspection_HalfYear（sup_rf_pm1monitorinspection）
- 《组分仪器工单规则》：颗粒物组分/PM1.docx
- 源码依据：实体 `Sup_RF_PM1MonitorInspection`、视图 `Sup_RF_PM1MonitorInspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `merror` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `btmodel` | 气压计 / ±10hPa | cshtml 标签 |
| `ftmodel` | 流量计 / ±5% | cshtml 标签 |
| `htmodel` | 湿度计 / ±5% | cshtml 标签 |
| `idvalue` | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 / 两周 | cshtml 标签 |
| `ttmodel` | 温度计 / ±2℃ | cshtml 标签 |
| `btnumber` | 气压计 / ±10hPa | cshtml 标签 |
| `formtype` | 表单类型 周 两周 月 季 半年 | 实体注释 |
| `ftnumber` | 流量计 / ±5% | cshtml 标签 |
| `htnumber` | 湿度计 / ±5% | cshtml 标签 |
| `icontent` | 检查内容 / 巡查周期 | cshtml 标签 |
| `pgtvalue` | 环境压力 / 仪器显示值 / 压力计显示值 / 是否校准 | cshtml 标签 |
| `ttnumber` | 温度计 / ±2℃ | cshtml 标签 |
| `shwhether` | 压头和垫块 / 采样头及切割头 / 是否漏气 | cshtml 标签 |
| `spwhether` | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 | cshtml 标签 |
| `btvalidity` | 气压计 / ±10hPa | cshtml 标签 |
| `flowdvalue` | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 / 两周 | cshtml 标签 |
| `ftvalidity` | 流量计 / ±5% | cshtml 标签 |
| `htvalidity` | 湿度计 / ±5% | cshtml 标签 |
| `idbwhether` | 压头和垫块 / 采样头及切割头 / 是否漏气 | cshtml 标签 |
| `ttvalidity` | 温度计 / ±2℃ | cshtml 标签 |
| `leakwhether` | 压头和垫块 / 采样头及切割头 / 是否漏气 | cshtml 标签 |
| `currentvalue` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `isitcomplete` | 流量计 / ±5% | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `originalvalue` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `tdisplayvalue` | 环境温度 / 仪器显示值 / 温度计显示值 / 是否校准 / 季度 | cshtml 标签 |
| `atdisplayvalue` | 环境温度 / 仪器显示值 / 温度计显示值 / 是否校准 / 季度 | cshtml 标签 |
| `btisitcomplete` | 气压计 / ±10hPa | cshtml 标签 |
| `htisitcomplete` | 湿度计 / ±5% | cshtml 标签 |
| `pgdisplayvalue` | 环境压力 / 仪器显示值 / 压力计显示值 / 是否校准 | cshtml 标签 |
| `thumidityvalue` | 环境湿度 / 仪器显示值 / 湿度计显示值 / 是否校准 | cshtml 标签 |
| `ttisitcomplete` | 温度计 / ±2℃ | cshtml 标签 |
| `athumidityvalue` | 环境湿度 / 仪器显示值 / 湿度计显示值 / 是否校准 | cshtml 标签 |
| `insideisitclean` | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 | cshtml 标签 |
| `ahisitcalibrated` | 环境湿度 / 仪器显示值 / 湿度计显示值 / 是否校准 | cshtml 标签 |
| `atisitcalibrated` | 环境温度 / 仪器显示值 / 温度计显示值 / 是否校准 / 季度 | cshtml 标签 |
| `calibrationpoint` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `dtisitcalibrated` | 数据传输 | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `ipisitcalibrated` | 仪器参数 | cshtml 标签 |
| `pgisitcalibrated` | 环境压力 / 仪器显示值 / 压力计显示值 / 是否校准 | cshtml 标签 |
| `externalisitclean` | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 | cshtml 标签 |
| `flowisitcalibrated` | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 / 两周 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |
| `alineisitcalibrated` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `papertapeisitcalibrated` | 纸带 | cshtml 标签 |


## Sup_RF_PM1MonitorInspection_Month（sup_rf_pm1monitorinspection）
- 《组分仪器工单规则》：颗粒物组分/PM1.docx
- 源码依据：实体 `Sup_RF_PM1MonitorInspection`、视图 `Sup_RF_PM1MonitorInspection.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `merror` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `btmodel` | 气压计 / ±10hPa | cshtml 标签 |
| `ftmodel` | 流量计 / ±5% | cshtml 标签 |
| `htmodel` | 湿度计 / ±5% | cshtml 标签 |
| `idvalue` | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 / 两周 | cshtml 标签 |
| `ttmodel` | 温度计 / ±2℃ | cshtml 标签 |
| `btnumber` | 气压计 / ±10hPa | cshtml 标签 |
| `formtype` | 表单类型 周 两周 月 季 半年 | 实体注释 |
| `ftnumber` | 流量计 / ±5% | cshtml 标签 |
| `htnumber` | 湿度计 / ±5% | cshtml 标签 |
| `icontent` | 检查内容 / 巡查周期 | cshtml 标签 |
| `pgtvalue` | 环境压力 / 仪器显示值 / 压力计显示值 / 是否校准 | cshtml 标签 |
| `ttnumber` | 温度计 / ±2℃ | cshtml 标签 |
| `shwhether` | 压头和垫块 / 采样头及切割头 / 是否漏气 | cshtml 标签 |
| `spwhether` | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 | cshtml 标签 |
| `btvalidity` | 气压计 / ±10hPa | cshtml 标签 |
| `flowdvalue` | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 / 两周 | cshtml 标签 |
| `ftvalidity` | 流量计 / ±5% | cshtml 标签 |
| `htvalidity` | 湿度计 / ±5% | cshtml 标签 |
| `idbwhether` | 压头和垫块 / 采样头及切割头 / 是否漏气 | cshtml 标签 |
| `ttvalidity` | 温度计 / ±2℃ | cshtml 标签 |
| `leakwhether` | 压头和垫块 / 采样头及切割头 / 是否漏气 | cshtml 标签 |
| `currentvalue` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `isitcomplete` | 流量计 / ±5% | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `originalvalue` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `tdisplayvalue` | 环境温度 / 仪器显示值 / 温度计显示值 / 是否校准 / 季度 | cshtml 标签 |
| `atdisplayvalue` | 环境温度 / 仪器显示值 / 温度计显示值 / 是否校准 / 季度 | cshtml 标签 |
| `btisitcomplete` | 气压计 / ±10hPa | cshtml 标签 |
| `htisitcomplete` | 湿度计 / ±5% | cshtml 标签 |
| `pgdisplayvalue` | 环境压力 / 仪器显示值 / 压力计显示值 / 是否校准 | cshtml 标签 |
| `thumidityvalue` | 环境湿度 / 仪器显示值 / 湿度计显示值 / 是否校准 | cshtml 标签 |
| `ttisitcomplete` | 温度计 / ±2℃ | cshtml 标签 |
| `athumidityvalue` | 环境湿度 / 仪器显示值 / 湿度计显示值 / 是否校准 | cshtml 标签 |
| `insideisitclean` | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 | cshtml 标签 |
| `ahisitcalibrated` | 环境湿度 / 仪器显示值 / 湿度计显示值 / 是否校准 | cshtml 标签 |
| `atisitcalibrated` | 环境温度 / 仪器显示值 / 温度计显示值 / 是否校准 / 季度 | cshtml 标签 |
| `calibrationpoint` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `dtisitcalibrated` | 数据传输 | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `ipisitcalibrated` | 仪器参数 | cshtml 标签 |
| `pgisitcalibrated` | 环境压力 / 仪器显示值 / 压力计显示值 / 是否校准 | cshtml 标签 |
| `externalisitclean` | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 | cshtml 标签 |
| `flowisitcalibrated` | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 / 两周 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |
| `alineisitcalibrated` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `papertapeisitcalibrated` | 纸带 | cshtml 标签 |


## Sup_RF_PM1MonitorInspection_Week（sup_rf_pm1monitorinspection）
- 《组分仪器工单规则》：颗粒物组分/PM1.docx
- 源码依据：实体 `Sup_RF_PM1MonitorInspection`、视图 `Sup_RF_PM1MonitorInspection.cshtml`、Vue 移植版 x3

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `merror` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `btmodel` | 气压计 / ±10hPa | cshtml 标签 |
| `ftmodel` | 流量计 / ±5% | cshtml 标签 |
| `htmodel` | 湿度计 / ±5% | cshtml 标签 |
| `idvalue` | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 / 两周 | cshtml 标签 |
| `ttmodel` | 温度计 / ±2℃ | cshtml 标签 |
| `btnumber` | 气压计 / ±10hPa | cshtml 标签 |
| `formtype` | 表单类型 周 两周 月 季 半年 | 实体注释 |
| `ftnumber` | 流量计 / ±5% | cshtml 标签 |
| `htnumber` | 湿度计 / ±5% | cshtml 标签 |
| `icontent` | 检查内容 / 巡查周期 | cshtml 标签 |
| `pgtvalue` | 环境压力 / 仪器显示值 / 压力计显示值 / 是否校准 | cshtml 标签 |
| `ttnumber` | 温度计 / ±2℃ | cshtml 标签 |
| `shwhether` | 压头和垫块 / 采样头及切割头 / 是否漏气 | cshtml 标签 |
| `spwhether` | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 | cshtml 标签 |
| `btvalidity` | 气压计 / ±10hPa | cshtml 标签 |
| `flowdvalue` | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 / 两周 | cshtml 标签 |
| `ftvalidity` | 流量计 / ±5% | cshtml 标签 |
| `htvalidity` | 湿度计 / ±5% | cshtml 标签 |
| `idbwhether` | 压头和垫块 / 采样头及切割头 / 是否漏气 | cshtml 标签 |
| `ttvalidity` | 温度计 / ±2℃ | cshtml 标签 |
| `leakwhether` | 压头和垫块 / 采样头及切割头 / 是否漏气 | cshtml 标签 |
| `currentvalue` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `isitcomplete` | 流量计 / ±5% | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `originalvalue` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `tdisplayvalue` | 环境温度 / 仪器显示值 / 温度计显示值 / 是否校准 / 季度 | cshtml 标签 |
| `atdisplayvalue` | 环境温度 / 仪器显示值 / 温度计显示值 / 是否校准 / 季度 | cshtml 标签 |
| `btisitcomplete` | 气压计 / ±10hPa | cshtml 标签 |
| `htisitcomplete` | 湿度计 / ±5% | cshtml 标签 |
| `pgdisplayvalue` | 环境压力 / 仪器显示值 / 压力计显示值 / 是否校准 | cshtml 标签 |
| `thumidityvalue` | 环境湿度 / 仪器显示值 / 湿度计显示值 / 是否校准 | cshtml 标签 |
| `ttisitcomplete` | 温度计 / ±2℃ | cshtml 标签 |
| `athumidityvalue` | 环境湿度 / 仪器显示值 / 湿度计显示值 / 是否校准 | cshtml 标签 |
| `insideisitclean` | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 | cshtml 标签 |
| `ahisitcalibrated` | 环境湿度 / 仪器显示值 / 湿度计显示值 / 是否校准 | cshtml 标签 |
| `atisitcalibrated` | 环境温度 / 仪器显示值 / 温度计显示值 / 是否校准 / 季度 | cshtml 标签 |
| `calibrationpoint` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `dtisitcalibrated` | 数据传输 | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `ipisitcalibrated` | 仪器参数 | cshtml 标签 |
| `pgisitcalibrated` | 环境压力 / 仪器显示值 / 压力计显示值 / 是否校准 | cshtml 标签 |
| `externalisitclean` | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 | cshtml 标签 |
| `flowisitcalibrated` | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 / 两周 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |
| `alineisitcalibrated` | 校准膜 / 校准点 / 原始值 / 本次值 / 测定误差 / 是否合格 | cshtml 标签 |
| `papertapeisitcalibrated` | 纸带 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_PM1MonitorInspection_HalfYear_PM1.vue）：**

bool_1 至 bool_6 分别为外部清洁、内部清洁、采样管路、压头和垫块、采样头及切割头、是否漏气； true = 原表单 0（是），false = 原表单 1（否）；remark 为其他；commonFile 为附件。

**Vue 头部字段映射（Sup_RF_PM1MonitorInspection_Month_PM1.vue）：**

string1 至 string4 为校准点、原始值、本次值、测定误差； bool_1 至 bool_7 为是否合格、外部清洁、内部清洁、采样管路、压头和垫块、采样头及切割头、是否漏气； true = 原表单 0（是），false = 原表单 1（否）；remark 为其他；commonFile 为附件。

**Vue 头部字段映射（Sup_RF_PM1MonitorInspection_Week_PM1.vue）：**

bool_1 至 bool_3 分别为数据传输、仪器参数、纸带； true = 原表单 0（是），false = 原表单 1（否）；remark 为其他；commonFile 为附件。


## Sup_RF_PRInspectionRecord（sup_rf_common）
- 源码依据：实体 `Sup_RF_PRInspectionRecord`、视图 `Sup_RF_PRInspectionRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 仪器状态（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_2` | 石英光学接收头清洁（视图标签：2 / 石英光学接收头清洁） | 实体注释 |
| `bool_3` | 石英光学接收头清洁（视图标签：3 / 仪器水汽情况检查） | 实体注释 |
| `bool_4` | 夜间信号检查（视图标签：4 / 夜间信号检查） | 实体注释 |
| `bool_5` | 微量泵工作状态（视图标签：5 / 微量泵工作状态） | 实体注释 |
| `bool_6` | 气密性检查（视图标签：6 / 气密性检查） | 实体注释 |
| `bool_7` | 干燥剂检查（视图标签：1 / 干燥剂检查） | 实体注释 |
| `bool_8` | 每月度维护检查（视图标签：有效 更换 / 维护检查（可多选于1项）） | 实体注释 |
| `bool_9` | 每年度维护检查（视图标签：维护检查（可多选于1项） / 每月度维护检查 是 否 （请填写第1部分）） | 实体注释 |
| `bool_10` | 检测器测量情况检查（视图标签：1 / 检测器测量情况检查） | 实体注释 |
| `bool_11` | 检测器稳定性（视图标签：2 / 检测器稳定性） | 实体注释 |
| `bool_12` | 仪器送检校准（视图标签：1 / 仪器送检校准） | 实体注释 |
| `string1` | 仪器状态 - 备注（视图标签：1 / 仪器状态） | 实体注释 |
| `string2` | 石英光学接收头清洁 - 备注（视图标签：2 / 石英光学接收头清洁） | 实体注释 |
| `string3` | 仪器水汽情况检查 - 备注（视图标签：3 / 仪器水汽情况检查） | 实体注释 |
| `string4` | 夜间信号检查 - 备注（视图标签：4 / 夜间信号检查） | 实体注释 |
| `string5` | 微量泵工作状态 - 备注（视图标签：5 / 微量泵工作状态） | 实体注释 |
| `string6` | 气密性检查 - 备注（视图标签：6 / 气密性检查） | 实体注释 |
| `string7` | 干燥剂检查 - 备注（视图标签：1 / 干燥剂检查） | 实体注释 |
| `string8` | 检测器测量情况检查 - 备注（视图标签：1 / 检测器测量情况检查） | 实体注释 |
| `string9` | 检测器稳定性 - 备注（视图标签：2 / 检测器稳定性） | 实体注释 |
| `string10` | 仪器送检校准 - 备注（视图标签：1 / 仪器送检校准） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_PTRMSWeekCheck（sup_rf_ptrmsweekcheck）
- 《组分仪器工单规则》：光化学组分/PTR-MS.docx
- 源码依据：实体 `Sup_RF_PTRMSWeekCheck`、视图 `Sup_RF_PTRMSWeekCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `date1` | 运维工程师： / 日期： | cshtml 标签 |
| `date2` | 业主代表： / 日期： | cshtml 标签 |
| `result1` | 1 / 自动分析仪及辅助设备的运行状态和主要技术参数 | cshtml 标签 |
| `result2` | 2 / 查看各仪表报警情况并记录报警内容 | cshtml 标签 |
| `result3` | 3 / 检查采样探头加热情况以及滤芯的受污染情况并对其气密性进行确认（重点检查） | cshtml 标签 |
| `result4` | 4 / 仪表风供应情况，内部管路畅通，仪器自动清洗装置，在线分析仪的进气管路和排气、排水管路清洁，必要时进行清洗，定期清洗取样泵和过滤网 | cshtml 标签 |
| `result5` | 5 / 站房内电路系统和通讯系统正常，对电源控制器、空调等辅助设备检查。 | cshtml 标签 |
| `result6` | 6 / 检查各仪器标准气体使用余量，是否需要添加，是否在有效期内，并按要求定期更换标准气体。 | cshtml 标签 |
| `result7` | 7 / 观察数据采集传输仪运行情况，并检查连接处有无损坏，对数据进行抽样检查，对比自动分析仪，数据采集传输仪及上位机（环保监控平台）接收到的数据是否一致。 | cshtml 标签 |
| `result8` | 8 / 检查各分析仪采样部分、计量单元、反应单元、加热单元、检测器单元的工作情况。 | cshtml 标签 |
| `result9` | 9 / 检查各分析仪的内部管路是否被污染，必要时进行清洗和维护。 | cshtml 标签 |
| `employer` | 业主代表： / 日期： | cshtml 标签 |
| `result10` | 10 / 检查差压变送器、压力变送器的零点是否发生变化。 | cshtml 标签 |
| `result11` | 11 / 保持监测站房、实验室的清洁，保持设备的清洁，避免仪器震动，监测站房的温度，湿度。 | cshtml 标签 |
| `operationengineer` | 运维工程师： / 日期： | cshtml 标签 |

**平台校验器：**`employer`=required；`operationengineer`=required


## Sup_RF_PTR_MSQuality（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/PTR-MS.docx;颗粒物组分/单颗粒飞行时间质谱.docx
- 源码依据：实体 `Sup_RF_PTR_MSQuality`、视图 `Sup_RF_PTR_MSQuality.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |


## Sup_RF_PaperTapeRecord（sup_rf_common）
- 源码依据：实体 `Sup_RF_PaperTapeRecord`、视图 `Sup_RF_PaperTapeRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 上一次 / 下一次 | cshtml 标签 |
| `time2` | 上一次 / 下一次 | cshtml 标签 |
| `string1` | 温度（视图标签：温度 / 湿度） | 实体注释 |
| `string2` | 湿度（视图标签：温度 / 湿度） | 实体注释 |
| `string3` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string4` | 出厂编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string5` | 监测项目（视图标签：上一次 / 下一次） | 实体注释 |
| `string6` | 1 / Pb | cshtml 标签 |
| `string7` | 1 / Pb | cshtml 标签 |
| `string8` | 2 / Se | cshtml 标签 |
| `string9` | 2 / Se | cshtml 标签 |
| `string10` | 3 / Hg | cshtml 标签 |
| `string11` | 3 / Hg | cshtml 标签 |
| `string12` | 4 / Fe | cshtml 标签 |
| `string13` | 4 / Fe | cshtml 标签 |
| `string14` | 5 / Co | cshtml 标签 |
| `string15` | 5 / Co | cshtml 标签 |
| `string16` | 6 / Ni | cshtml 标签 |
| `string17` | 6 / Ni | cshtml 标签 |
| `string18` | 7 / Cu | cshtml 标签 |
| `string19` | 7 / Cu | cshtml 标签 |
| `string20` | 8 / Zn | cshtml 标签 |
| `string21` | 8 / Zn | cshtml 标签 |
| `string22` | 9 / Tl | cshtml 标签 |
| `string23` | 9 / Tl | cshtml 标签 |
| `string24` | 10 / As | cshtml 标签 |
| `string25` | 10 / As | cshtml 标签 |
| `string26` | 11 / Br | cshtml 标签 |
| `string27` | 11 / Br | cshtml 标签 |
| `string28` | 12 / Mo | cshtml 标签 |
| `string29` | 12 / Mo | cshtml 标签 |
| `string30` | 13 / Ga | cshtml 标签 |
| `string31` | 13 / Ga | cshtml 标签 |
| `string32` | 14 / K | cshtml 标签 |
| `string33` | 14 / K | cshtml 标签 |
| `string34` | 15 / Ca | cshtml 标签 |
| `string35` | 15 / Ca | cshtml 标签 |
| `string36` | 16 / Sc | cshtml 标签 |
| `string37` | 16 / Sc | cshtml 标签 |
| `string38` | 17 / Ti | cshtml 标签 |
| `string39` | 17 / Ti | cshtml 标签 |
| `string40` | 18 / Ba | cshtml 标签 |
| `string41` | 18 / Ba | cshtml 标签 |
| `string42` | 19 / V | cshtml 标签 |
| `string43` | 19 / V | cshtml 标签 |
| `string44` | 20 / Cr | cshtml 标签 |
| `string45` | 20 / Cr | cshtml 标签 |
| `string46` | 21 / Mn | cshtml 标签 |
| `string47` | 21 / Mn | cshtml 标签 |
| `string48` | 22 / Cs | cshtml 标签 |
| `string49` | 22 / Cs | cshtml 标签 |
| `string50` | 23 / Al | cshtml 标签 |
| `string51` | 23 / Al | cshtml 标签 |
| `string52` | 24 / Si | cshtml 标签 |
| `string53` | 24 / Si | cshtml 标签 |
| `string54` | 25 / Pd | cshtml 标签 |
| `string55` | 25 / Pd | cshtml 标签 |
| `string56` | 26 / Ag | cshtml 标签 |
| `string57` | 26 / Ag | cshtml 标签 |
| `string58` | 27 / Cd | cshtml 标签 |
| `string59` | 27 / Cd | cshtml 标签 |
| `string60` | 28 / Sn | cshtml 标签 |
| `string61` | 28 / Sn | cshtml 标签 |
| `string62` | 29 / Sb | cshtml 标签 |
| `string63` | 29 / Sb | cshtml 标签 |
| `string64` | 30 / Te | cshtml 标签 |
| `string65` | 30 / Te | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string4`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string46`=required；`string47`=required；`string48`=required；`string49`=required；`string5`=required；`string50`=required；`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required；`string56`=required；`string57`=required；`string58`=required；`string59`=required；`string6`=required；`string60`=required；`string61`=required；`string62`=required；`string63`=required；`string64`=required；`string65`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_QualityCheck（sup_rf_common）
- 源码依据：实体 `Sup_RF_QualityCheck`、视图 `Sup_RF_QualityCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 重金属分析仪资料上一次核查日期（视图标签：PM2.5中重金属 / 上一次 / 下一次） | 实体注释 |
| `time2` | 重金属分析仪资料下一次核查日期（视图标签：PM2.5中重金属 / 上一次 / 下一次） | 实体注释 |
| `string1` | 温度（视图标签：温度 / 湿度） | 实体注释 |
| `string2` | 湿度（视图标签：温度 / 湿度） | 实体注释 |
| `string3` | 仪器型号（视图标签：PM2.5中重金属 / 上一次 / 下一次） | 实体注释 |
| `string4` | 出厂编号（视图标签：PM2.5中重金属 / 上一次 / 下一次） | 实体注释 |
| `string5` | 滤光片1 - 膜片名称（视图标签：滤光片1 / 1） | 实体注释 |
| `string6` | 滤光片1 - 运行时间（sec)（视图标签：滤光片1 / 1） | 实体注释 |
| `string7` | 滤光片1 - 标准浓度（ng）（视图标签：滤光片1 / 1） | 实体注释 |
| `string8` | 滤光片1 - 测量浓度1（视图标签：滤光片1 / 1） | 实体注释 |
| `string9` | 滤光片1 - 偏差1（视图标签：滤光片1 / 1） | 实体注释 |
| `string10` | 滤光片1 - 测量浓度2 | 实体注释 |
| `string11` | 滤光片1 - 偏差2 | 实体注释 |
| `string12` | 滤光片1 - 测量浓度3 | 实体注释 |
| `string13` | 滤光片1 - 偏差3 | 实体注释 |
| `string14` | 滤光片1 - 测量浓度平均值 | 实体注释 |
| `string15` | 滤光片1 - 偏差平均值 | 实体注释 |
| `string16` | 滤光片2 - 膜片名称（视图标签：滤光片2 / 1） | 实体注释 |
| `string17` | 滤光片2 - 运行时间（视图标签：滤光片2 / 1） | 实体注释 |
| `string18` | 滤光片2 - 标准浓度（视图标签：滤光片2 / 1） | 实体注释 |
| `string19` | 滤光片2 - 测量浓度1（视图标签：滤光片2 / 1） | 实体注释 |
| `string20` | 滤光片2 - 偏差1（视图标签：滤光片2 / 1） | 实体注释 |
| `string21` | 滤光片2 - 测量浓度2 | 实体注释 |
| `string22` | 滤光片2 - 偏差2 | 实体注释 |
| `string23` | 滤光片2 - 测量浓度3 | 实体注释 |
| `string24` | 滤光片2 - 偏差3 | 实体注释 |
| `string25` | 滤光片2 - 测量浓度平均值 | 实体注释 |
| `string26` | 滤光片2 - 偏差平均值 | 实体注释 |
| `string27` | 滤光片3 - 膜片名称（视图标签：滤光片3 / 1） | 实体注释 |
| `string28` | 滤光片3 - 运行时间（视图标签：滤光片3 / 1） | 实体注释 |
| `string29` | 滤光片3 - 标准浓度（视图标签：滤光片3 / 1） | 实体注释 |
| `string30` | 滤光片3 - 测量浓度1（视图标签：滤光片3 / 1） | 实体注释 |
| `string31` | 滤光片3 - 偏差1（视图标签：滤光片3 / 1） | 实体注释 |
| `string32` | 滤光片3 - 测量浓度2 | 实体注释 |
| `string33` | 滤光片3 - 偏差2 | 实体注释 |
| `string34` | 滤光片3 - 测量浓度3 | 实体注释 |
| `string35` | 滤光片3 - 偏差3 | 实体注释 |
| `string36` | 滤光片3 - 测量浓度平均值 | 实体注释 |
| `string37` | 滤光片3 - 偏差平均值 | 实体注释 |
| `string38` | 滤光片4 - 膜片名称（视图标签：滤光片4 / 1） | 实体注释 |
| `string39` | 滤光片4 - 运行时间（视图标签：滤光片4 / 1） | 实体注释 |
| `string40` | 滤光片4 - 标准浓度（视图标签：滤光片4 / 1） | 实体注释 |
| `string41` | 滤光片4 - 测量浓度1（视图标签：滤光片4 / 1） | 实体注释 |
| `string42` | 滤光片4 - 偏差1（视图标签：滤光片4 / 1） | 实体注释 |
| `string43` | 滤光片4 - 测量浓度2 | 实体注释 |
| `string44` | 滤光片4 - 偏差2 | 实体注释 |
| `string45` | 滤光片4 - 测量浓度3 | 实体注释 |
| `string46` | 滤光片4 - 偏差3 | 实体注释 |
| `string47` | 滤光片4 - 测量浓度平均值 | 实体注释 |
| `string48` | 滤光片4 - 偏差平均值 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string4`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string46`=required；`string47`=required；`string48`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_Quarter_HONOCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/HONO.docx
- 源码依据：实体 `Sup_RF_Quarter_HONOCheck`、视图 `Sup_RF_Quarter_HONOCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：维护单位 / 安装地点 / 维护时间） | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 1 / 仪器检查 / 分析仪主机供电 | cshtml 标签 |
| `bool_2` | 循环水浴供电及水位高度 | cshtml 标签 |
| `bool_3` | 分析电脑供电 | cshtml 标签 |
| `bool_4` | 取气盒管路连接及固定 | cshtml 标签 |
| `bool_5` | 2 / 系统检查 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `bool_6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `bool_7` | 泵头转速是否正常 | cshtml 标签 |
| `bool_8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `bool_9` | 泵管卡子松紧度 | cshtml 标签 |
| `bool_10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `bool_11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `bool_12` | 安全瓶 / 无进液 | cshtml 标签 |
| `bool_13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `bool_14` | 光源LED / 正常光照 | cshtml 标签 |
| `bool_15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `bool_16` | 红色线是否达到预计值 | cshtml 标签 |
| `bool_17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `bool_18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `bool_19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `bool_20` | 测量数据偏离 | cshtml 标签 |
| `bool_21` | 是否存在异常数据 | cshtml 标签 |
| `bool_22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `bool_23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `bool_24` | R2避光保护 | cshtml 标签 |
| `bool_25` | 外表无破损 | cshtml 标签 |
| `bool_26` | 试剂 / 是否过期 | cshtml 标签 |
| `bool_27` | 配置是否准确 | cshtml 标签 |
| `bool_28` | 剩余量是否充足 | cshtml 标签 |
| `bool_29` | 空气过滤膜 / 检查是否需要更换 | cshtml 标签 |
| `remark1` | 1 / 仪器检查 / 分析仪主机供电 | cshtml 标签 |
| `remark2` | 循环水浴供电及水位高度 | cshtml 标签 |
| `remark3` | 分析电脑供电 | cshtml 标签 |
| `remark4` | 取气盒管路连接及固定 | cshtml 标签 |
| `remark5` | 2 / 系统检查 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `remark6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `remark7` | 泵头转速是否正常 | cshtml 标签 |
| `remark8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `remark9` | 泵管卡子松紧度 | cshtml 标签 |
| `string1` | 1 / 仪器检查 / 分析仪主机供电 | cshtml 标签 |
| `string2` | 循环水浴供电及水位高度 | cshtml 标签 |
| `string3` | 分析电脑供电 | cshtml 标签 |
| `string4` | 取气盒管路连接及固定 | cshtml 标签 |
| `string5` | 2 / 系统检查 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `string6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `string7` | 泵头转速是否正常 | cshtml 标签 |
| `string8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `string9` | 泵管卡子松紧度 | cshtml 标签 |
| `remark10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `remark11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `remark12` | 安全瓶 / 无进液 | cshtml 标签 |
| `remark13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `remark14` | 光源LED / 正常光照 | cshtml 标签 |
| `remark15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `remark16` | 红色线是否达到预计值 | cshtml 标签 |
| `remark17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `remark18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `remark19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `remark20` | 测量数据偏离 | cshtml 标签 |
| `remark21` | 是否存在异常数据 | cshtml 标签 |
| `remark22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `remark23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `remark24` | R2避光保护 | cshtml 标签 |
| `remark25` | 外表无破损 | cshtml 标签 |
| `remark26` | 试剂 / 是否过期 | cshtml 标签 |
| `remark27` | 配置是否准确 | cshtml 标签 |
| `remark28` | 剩余量是否充足 | cshtml 标签 |
| `remark29` | 空气过滤膜 / 检查是否需要更换 | cshtml 标签 |
| `remark49` | 异常问题处理记录： | cshtml 标签 |
| `remark50` | 备注： | cshtml 标签 |
| `string10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `string11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `string12` | 安全瓶 / 无进液 | cshtml 标签 |
| `string13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `string14` | 光源LED / 正常光照 | cshtml 标签 |
| `string15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `string16` | 红色线是否达到预计值 | cshtml 标签 |
| `string17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `string18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `string19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `string20` | 测量数据偏离 | cshtml 标签 |
| `string21` | 是否存在异常数据 | cshtml 标签 |
| `string22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `string23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `string24` | R2避光保护 | cshtml 标签 |
| `string25` | 外表无破损 | cshtml 标签 |
| `string26` | 试剂 / 是否过期 | cshtml 标签 |
| `string27` | 配置是否准确 | cshtml 标签 |
| `string28` | 剩余量是否充足 | cshtml 标签 |
| `string29` | 空气过滤膜 / 检查是否需要更换 | cshtml 标签 |
| `string51` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string52` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string53` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string54` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string55` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |

**平台校验器：**`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required


## Sup_RF_Quarter_YT_NMHCRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/甲烷非甲烷.docx
- 源码依据：实体 `Sup_RF_Quarter_YT_NMHCRecord`、视图 `Sup_RF_Quarter_YT_NMHCRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次校准日期（视图标签：甲烷钢瓶气编号 / 甲烷钢瓶气浓度 / 有效期） | 实体注释 |
| `time2` | 参考流量计 - 下一次校准日期（视图标签：丙烷钢瓶气编号 / 丙烷钢瓶气浓度 / 有效期） | 实体注释 |
| `time3` | OCEC分析仪资料 - 上一次校准时间（视图标签：开始时间： / 结束时间：） | 实体注释 |
| `time4` | OCEC分析仪资料 - 下一次校准时间（视图标签：开始时间： / 结束时间：） | 实体注释 |
| `string1` | 设备型号（视图标签：多点校准仪型号 / 多点校准仪编号） | 实体注释 |
| `string2` | 出厂编号（视图标签：多点校准仪型号 / 多点校准仪编号） | 实体注释 |
| `string3` | 斜率（视图标签：零气发生器型号 / 零气发生器编号） | 实体注释 |
| `string4` | 截距（视图标签：零气发生器型号 / 零气发生器编号） | 实体注释 |
| `string5` | 相关系数（视图标签：甲烷钢瓶气编号 / 甲烷钢瓶气浓度 / 有效期） | 实体注释 |
| `string6` | 仪器型号（视图标签：甲烷钢瓶气编号 / 甲烷钢瓶气浓度 / 有效期） | 实体注释 |
| `string7` | 出厂编号（视图标签：丙烷钢瓶气编号 / 丙烷钢瓶气浓度 / 有效期） | 实体注释 |
| `string8` | 监测项目（视图标签：丙烷钢瓶气编号 / 丙烷钢瓶气浓度 / 有效期） | 实体注释 |
| `string9` | 设定流量 - 氦气（视图标签：室内温湿度及气压） | 实体注释 |
| `string10` | 显示流量 - 氦气（视图标签：室内温湿度及气压） | 实体注释 |
| `string11` | 参考流量计读数 - 氦气（视图标签：室内温湿度及气压） | 实体注释 |
| `string12` | 参考流量计修正 - 氦气（视图标签：记录人：） | 实体注释 |
| `string13` | 误差 - 氦气（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string14` | 检查结果 - 氦气（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string15` | 设定流量 - 氦气（吹扫）（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string16` | 显示流量 - 氦气（吹扫）（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string17` | 参考流量计读数 - 氦气（吹扫）（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string18` | 参考流量计修正 - 氦气（吹扫）（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string19` | 误差 - 氦气（吹扫）（视图标签：相关系数 （要求：R≥0.999）） | 实体注释 |
| `string20` | 检查结果 - 氦气（吹扫）（视图标签：各浓度点回测最大偏差（要求：≤±10%）） | 实体注释 |
| `string21` | 设定流量 - 氦氧（视图标签：结论） | 实体注释 |
| `string22` | 显示流量 - 氦氧（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string23` | 参考流量计读数 - 氦氧（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string24` | 参考流量计修正 - 氦氧（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string25` | 误差 - 氦氧（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string26` | 检查结果 - 氦氧（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string27` | 设定流量 - 氦甲烷（视图标签：响应值5 / 响应值6） | 实体注释 |
| `string28` | 显示流量 - 氦甲烷（视图标签：相关系数 （要求：R≥0.999）） | 实体注释 |
| `string29` | 参考流量计读数 - 氦甲烷（视图标签：各浓度点回测最大偏差（要求：≤±10%）） | 实体注释 |
| `string30` | 参考流量计修正 - 氦甲烷（视图标签：结论） | 实体注释 |
| `string31` | 误差 - 氦甲烷 | 实体注释 |
| `string32` | 检查结果 - 氦甲烷 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_QuarterlyEquipment（sup_rf_quarterlyequipment）
- 源码依据：实体 `Sup_RF_QuarterlyEquipment`、视图 `Sup_RF_QuarterlyEquipment.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `date1` | 上一次 / 下一次 | cshtml 标签 |
| `date2` | 上一次 / 下一次 | cshtml 标签 |
| `date3` | 甲醛标液 | cshtml 标签 |
| `date4` | 甲醛标液 | cshtml 标签 |
| `date5` | 上次校准日期 / 甲醛摩尔质量(g/mol) / 30.03 | cshtml 标签 |
| `bool_1` | 1 / 颗粒物过滤器更换 / 仅适用雪迪龙 | cshtml 标签 |
| `bool_2` | 2 / 蠕动泵泵管 / 每季度至少更换一次（仅适用伊创：MSP3、5） | cshtml 标签 |
| `bool_3` | 3 / 蠕动泵泵管润滑油 / 每次更换泵管时使用 | cshtml 标签 |
| `bool_4` | 4 / 液体流量检查 / 误差≤±5% | cshtml 标签 |
| `bool_5` | 5 / 多点线性检查 / R 2 ≥0.99 | cshtml 标签 |
| `remark1` | 1 / 颗粒物过滤器更换 / 仅适用雪迪龙 | cshtml 标签 |
| `remark2` | 2 / 蠕动泵泵管 / 每季度至少更换一次（仅适用伊创：MSP3、5） | cshtml 标签 |
| `remark3` | 3 / 蠕动泵泵管润滑油 / 每次更换泵管时使用 | cshtml 标签 |
| `remark4` | 4 / 液体流量检查 / 误差≤±5% | cshtml 标签 |
| `remark5` | 5 / 多点线性检查 / R 2 ≥0.99 | cshtml 标签 |
| `remark6` | 6 / 重复性测试 / 相对标准差≤5% | cshtml 标签 |
| `remark7` | 7 / 检出限测试 / 检出限≤100ppt | cshtml 标签 |
| `string1` | 上一次 / 下一次 | cshtml 标签 |
| `string2` | 上一次 / 下一次 | cshtml 标签 |
| `string3` | 1 | cshtml 标签 |
| `string4` | 1 | cshtml 标签 |
| `string5` | 1 | cshtml 标签 |
| `string6` | 1 | cshtml 标签 |
| `string7` | 1 | cshtml 标签 |
| `string8` | 1 | cshtml 标签 |
| `string9` | 2 | cshtml 标签 |
| `string10` | 2 | cshtml 标签 |
| `string11` | 2 | cshtml 标签 |
| `string12` | 2 | cshtml 标签 |
| `string13` | 2 | cshtml 标签 |
| `string14` | 2 | cshtml 标签 |
| `string15` | 3 | cshtml 标签 |
| `string16` | 3 | cshtml 标签 |
| `string17` | 3 | cshtml 标签 |
| `string18` | 3 | cshtml 标签 |
| `string19` | 3 | cshtml 标签 |
| `string20` | 3 | cshtml 标签 |
| `string21` | 平均值 / / / / | cshtml 标签 |
| `string22` | 平均值 / / / / | cshtml 标签 |
| `string23` | 平均值 / / / / | cshtml 标签 |
| `string24` | 平均值 / / / / | cshtml 标签 |
| `string25` | 甲醛标液 | cshtml 标签 |
| `string26` | 甲醛标液 | cshtml 标签 |
| `string27` | 吸收液流量（ml/min） / 仪器显示采样流量（L/min） | cshtml 标签 |
| `string28` | 吸收液流量（ml/min） / 仪器显示采样流量（L/min） | cshtml 标签 |
| `string29` | 吸收效率 / 气体摩尔体积系数（L/mol） | cshtml 标签 |
| `string30` | 吸收效率 / 气体摩尔体积系数（L/mol） | cshtml 标签 |
| `string31` | 零点 | cshtml 标签 |
| `string32` | 零点 | cshtml 标签 |
| `string33` | 零点 | cshtml 标签 |
| `string34` | 零点 | cshtml 标签 |
| `string35` | 零点 | cshtml 标签 |
| `string36` | 浓度点1 | cshtml 标签 |
| `string37` | 浓度点1 | cshtml 标签 |
| `string38` | 浓度点1 | cshtml 标签 |
| `string39` | 浓度点1 | cshtml 标签 |
| `string40` | 浓度点1 | cshtml 标签 |
| `string41` | 浓度点2 | cshtml 标签 |
| `string42` | 浓度点2 | cshtml 标签 |
| `string43` | 浓度点2 | cshtml 标签 |
| `string44` | 浓度点2 | cshtml 标签 |
| `string45` | 浓度点2 | cshtml 标签 |
| `string46` | 浓度点3 | cshtml 标签 |
| `string47` | 浓度点3 | cshtml 标签 |
| `string48` | 浓度点3 | cshtml 标签 |
| `string49` | 浓度点3 | cshtml 标签 |
| `string50` | 浓度点3 | cshtml 标签 |
| `string51` | 浓度点4 | cshtml 标签 |
| `string52` | 浓度点4 | cshtml 标签 |
| `string53` | 浓度点4 | cshtml 标签 |
| `string54` | 浓度点4 | cshtml 标签 |
| `string55` | 浓度点4 | cshtml 标签 |
| `string56` | 斜率 / 截距 / 相关系数 | cshtml 标签 |
| `string57` | 斜率 / 截距 / 相关系数 | cshtml 标签 |
| `string58` | 斜率 / 截距 / 相关系数 | cshtml 标签 |
| `string61` | 6 / 重复性测试 / 相对标准差≤5% | cshtml 标签 |
| `string62` | 7 / 检出限测试 / 检出限≤100ppt | cshtml 标签 |
| `string63` | 1 | cshtml 标签 |
| `string64` | 1 | cshtml 标签 |
| `string65` | 1 | cshtml 标签 |
| `string66` | 1 | cshtml 标签 |
| `string67` | 1 | cshtml 标签 |
| `string68` | 2 | cshtml 标签 |
| `string69` | 2 | cshtml 标签 |
| `string70` | 2 | cshtml 标签 |
| `string71` | 3 | cshtml 标签 |
| `string72` | 3 | cshtml 标签 |
| `string73` | 3 | cshtml 标签 |
| `string74` | 4 | cshtml 标签 |
| `string75` | 4 | cshtml 标签 |
| `string76` | 4 | cshtml 标签 |
| `string77` | 5 | cshtml 标签 |
| `string78` | 5 | cshtml 标签 |
| `string79` | 5 | cshtml 标签 |
| `string80` | 6 | cshtml 标签 |
| `string81` | 6 | cshtml 标签 |
| `string82` | 6 | cshtml 标签 |
| `string83` | 7 | cshtml 标签 |
| `string84` | 7 | cshtml 标签 |
| `string85` | 7 | cshtml 标签 |
| `string86` | 平均值 / / / / / / | cshtml 标签 |
| `string87` | 平均值 / / / / / / | cshtml 标签 |
| `string88` | 1 | cshtml 标签 |
| `string89` | 1 | cshtml 标签 |
| `string90` | 1 | cshtml 标签 |
| `string91` | 1 | cshtml 标签 |
| `string92` | 1 | cshtml 标签 |
| `string93` | 2 | cshtml 标签 |
| `string94` | 2 | cshtml 标签 |
| `string95` | 2 | cshtml 标签 |
| `string96` | 3 | cshtml 标签 |
| `string97` | 3 | cshtml 标签 |
| `string98` | 3 | cshtml 标签 |
| `string99` | 4 | cshtml 标签 |
| `string100` | 4 | cshtml 标签 |
| `string101` | 4 | cshtml 标签 |
| `string102` | 5 | cshtml 标签 |
| `string103` | 5 | cshtml 标签 |
| `string104` | 5 | cshtml 标签 |
| `string105` | 6 | cshtml 标签 |
| `string106` | 6 | cshtml 标签 |
| `string107` | 6 | cshtml 标签 |
| `string108` | 7 | cshtml 标签 |
| `string109` | 7 | cshtml 标签 |
| `string110` | 7 | cshtml 标签 |
| `string111` | 平均值 / / / / / / | cshtml 标签 |
| `string112` | 平均值 / / / / / / | cshtml 标签 |
| `string113` | 液体甲醛浓度MDL(μg/L) / 气体甲醛浓度MDL(ppb) | cshtml 标签 |
| `string114` | 液体甲醛浓度MDL(μg/L) / 气体甲醛浓度MDL(ppb) | cshtml 标签 |
| `string115` | 零点 | cshtml 标签 |
| `string116` | 浓度点1 | cshtml 标签 |
| `string117` | 浓度点2 | cshtml 标签 |
| `string118` | 浓度点3 | cshtml 标签 |
| `string119` | 浓度点4 | cshtml 标签 |

**平台校验器：**`string1`=required；`string10`=required；`string100`=required；`string101`=required；`string102`=required；`string103`=required；`string104`=required；`string105`=required；`string106`=required；`string107`=required；`string108`=required；`string109`=required；`string11`=required；`string110`=required；`string111`=required；`string112`=required；`string113`=required；`string114`=required；`string115`=required；`string116`=required；`string117`=required；`string118`=required；`string119`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string4`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string46`=required；`string47`=required；`string48`=required；`string49`=required；`string5`=required；`string50`=required；`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required；`string56`=required；`string57`=required；`string58`=required；`string6`=required；`string63`=required；`string64`=required；`string65`=required；`string66`=required；`string67`=required；`string68`=required；`string69`=required；`string7`=required；`string70`=required；`string71`=required；`string72`=required；`string73`=required；`string74`=required；`string75`=required；`string76`=required；`string77`=required；`string78`=required；`string79`=required；`string8`=required；`string80`=required；`string81`=required；`string82`=required；`string83`=required；`string84`=required；`string85`=required；`string86`=required；`string87`=required；`string88`=required；`string89`=required；`string9`=required；`string90`=required；`string91`=required；`string92`=required；`string93`=required；`string94`=required；`string95`=required；`string96`=required；`string97`=required；`string98`=required；`string99`=required


## Sup_RF_RULEITEMVOCs（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_RULEITEMVOCs`、视图 `Sup_RF_RULEITEMVOCs.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 仪器状态-高碳（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_2` | 仪器状态-低碳（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_3` | 炉温是否升到200℃-高碳（视图标签：4 / 炉温是否升到200℃） | 实体注释 |
| `bool_4` | 炉温是否升到200℃-低碳（视图标签：4 / 炉温是否升到200℃） | 实体注释 |
| `bool_5` | 升温过程是否平稳-高碳（视图标签：5 / 升温过程是否平稳） | 实体注释 |
| `bool_6` | 升温过程是否平稳-低碳（视图标签：5 / 升温过程是否平稳） | 实体注释 |
| `bool_7` | FID温度波动范围-高碳（视图标签：8 / FID温度波动范围 / (179.5-180.5℃)） | 实体注释 |
| `bool_8` | FID温度波动范围-低碳（视图标签：8 / FID温度波动范围 / (179.5-180.5℃)） | 实体注释 |
| `bool_9` | 校准仪状态（视图标签：1 / 校准仪状态） | 实体注释 |
| `bool_10` | 零气泵分压（4bar）（视图标签：3 / 零气泵分压（4bar）） | 实体注释 |
| `bool_11` | 零气泵排水（视图标签：4 / 零气泵排水） | 实体注释 |
| `bool_12` | 零气泵启动阀（视图标签：5 / 零气泵启动阀） | 实体注释 |
| `bool_13` | 氢气发生器状态（视图标签：6 / 氢气发生器状态） | 实体注释 |
| `bool_14` | 氢气发生器输出压力（视图标签：7 / 氢气发生器输出压力 / （3bar）） | 实体注释 |
| `bool_15` | 氢气发生器输出压力（视图标签：1 / 氢气发生器添加纯水） | 实体注释 |
| `bool_16` | 颗粒物过滤膜（视图标签：2 / 颗粒物过滤膜） | 实体注释 |
| `string1` | 仪器状态-备注（视图标签：1 / 仪器状态） | 实体注释 |
| `string2` | 采样流量（Nml/min）- 高碳（视图标签：2 / 采样流量（Nml/min）） | 实体注释 |
| `string3` | 采样流量（Nml/min）- 低碳（视图标签：2 / 采样流量（Nml/min）） | 实体注释 |
| `string4` | 采样流量（Nml/min）- 备注（视图标签：2 / 采样流量（Nml/min）） | 实体注释 |
| `string5` | 柱压（bar）- 高碳（视图标签：3 / 柱压（bar）） | 实体注释 |
| `string6` | 柱压（bar）- 低碳（视图标签：3 / 柱压（bar）） | 实体注释 |
| `string7` | 柱压（bar）- 备注（视图标签：3 / 柱压（bar）） | 实体注释 |
| `string8` | 炉温是否升到200℃ - 备注（视图标签：4 / 炉温是否升到200℃） | 实体注释 |
| `string9` | 升温过程是否平稳 - 备注（视图标签：5 / 升温过程是否平稳） | 实体注释 |
| `string10` | 吸附管温度 - 高碳（视图标签：6 / 吸附管温度） | 实体注释 |
| `string11` | 吸附管温度 - 低碳（视图标签：6 / 吸附管温度） | 实体注释 |
| `string12` | 吸附管温度 - 备注（视图标签：6 / 吸附管温度） | 实体注释 |
| `string13` | 聚焦管温度 - 低碳（视图标签：7 / 聚焦管温度） | 实体注释 |
| `string14` | 聚焦管温度 - 备注（视图标签：7 / 聚焦管温度） | 实体注释 |
| `string15` | FID信号值 - 高碳（视图标签：9 / FID信号值） | 实体注释 |
| `string16` | FID信号值 - 低碳（视图标签：9 / FID信号值） | 实体注释 |
| `string17` | FID信号值 - 备注（视图标签：9 / FID信号值） | 实体注释 |
| `string18` | 校准仪状态 - 备注（视图标签：1 / 校准仪状态） | 实体注释 |
| `string19` | 零气泵压力（bar）- 内容（视图标签：2 / 零气泵压力（bar）） | 实体注释 |
| `string20` | 零气泵压力（bar）- 备注（视图标签：2 / 零气泵压力（bar）） | 实体注释 |
| `string21` | 零气泵分压（4bar）- 备注（视图标签：3 / 零气泵分压（4bar）） | 实体注释 |
| `string22` | 零气泵排水 - 备注（视图标签：4 / 零气泵排水） | 实体注释 |
| `string23` | 零气泵启动阀 - 备注（视图标签：5 / 零气泵启动阀） | 实体注释 |
| `string24` | 氢气发生器状态 - 备注（视图标签：6 / 氢气发生器状态） | 实体注释 |
| `string25` | 氢气发生器添加纯水 - 备注（视图标签：1 / 氢气发生器添加纯水） | 实体注释 |
| `string26` | 颗粒物过滤膜 - 备注（视图标签：2 / 颗粒物过滤膜） | 实体注释 |
| `string27` | 备注（视图标签：备注：） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string10`=required,double；`string11`=required,double；`string13`=required,double；`string15`=required,double；`string16`=required,double；`string19`=required,double；`string2`=required,double；`string3`=required,double；`string5`=required,double；`string6`=required,double


## Sup_RF_RepaireRecord（sup_rf_repairerecord）
- 源码依据：实体 `Sup_RF_RepaireRecord`、视图 `Sup_RF_RepaireRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `faulttime` | 故障时间： | cshtml 标签 |
| `recovertime` | 仪器恢复运行时间： | cshtml 标签 |
| `repairetime` | 现场检修时间： | cshtml 标签 |
| `faultcontent` | 故障现象： | cshtml 标签 |
| `hasfaultpart` | 是否有故障配件： / 维修后仪器状态： | cshtml 标签 |
| `repairecontent` | 现场检修结果： | cshtml 标签 |


## Sup_RF_SpeedMeterMaintain（sup_rf_speedmetermaintain）
- 源码依据：实体 `Sup_RF_SpeedMeterMaintain`、视图 `Sup_RF_SpeedMeterMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remarks` | 备注 | cshtml 标签 |
| `cfremarks` | 2.检查光纤出口是否有亮光？ | cshtml 标签 |
| `cpremarks` | 校准 / 1.是否进行暗噪声校准？（每月 做一次） | cshtml 标签 |
| `dfremarks` | 5.查看数据储存盘是否已满？ | cshtml 标签 |
| `snremarks` | 2.光谱图是否正常？ | cshtml 标签 |
| `wnremarks` | 3.站房及设施是否清洁干净？ | cshtml 标签 |
| `cclremarks` | 3.检查通讯线（带磁环USB线）接头接 触是否正常？ | cshtml 标签 |
| `dctremarks` | 设备检 查 / 1.检测器控制温度（4～6℃） | cshtml 标签 |
| `icsremarks` | 谱图及 数据 / 1.分析仪与工控机是否连接成功？ | cshtml 标签 |
| `idcremarks` | 7.原始数据是否与数据采集到的数 据一致 | cshtml 标签 |
| `ircremarks` | 5.接收头是否进行清 理？（每周清理一次） | cshtml 标签 |
| `itnremarks` | 4.检查/更换干燥剂 | cshtml 标签 |
| `itsremarks` | 3.测量物种是否正确（JO1D、 JHCHO_M、JNO2、JH2O2、JHONO 、JNO3_M、JHCHO_R、JNO_R） | cshtml 标签 |
| `nsrremarks` | 6.夜间信号范围（-10E-4～10E- 4） | cshtml 标签 |
| `nstremarks` | 室内外 环境 / 1.监测站内温度(20～30℃) | cshtml 标签 |
| `wnmremarks` | 校准 / 1.是否进行暗噪声校准？（每月 做一次） | cshtml 标签 |
| `acstremarks` | 2.空调设置温度(18～26℃) | cshtml 标签 |
| `itaaremarks` | 4.查看历史数据是否有异常或者缺 失？ | cshtml 标签 |
| `itnsremarks` | 6.网络是否开正常？ | cshtml 标签 |
| `cfisitnormal` | 2.检查光纤出口是否有亮光？ | cshtml 标签 |
| `cpisitnormal` | 校准 / 1.是否进行暗噪声校准？（每月 做一次） | cshtml 标签 |
| `dfisitnormal` | 5.查看数据储存盘是否已满？ | cshtml 标签 |
| `snisitnormal` | 2.光谱图是否正常？ | cshtml 标签 |
| `wnisitnormal` | 3.站房及设施是否清洁干净？ | cshtml 标签 |
| `cclisitnormal` | 3.检查通讯线（带磁环USB线）接头接 触是否正常？ | cshtml 标签 |
| `dctisitnormal` | 设备检 查 / 1.检测器控制温度（4～6℃） | cshtml 标签 |
| `icsisitnormal` | 谱图及 数据 / 1.分析仪与工控机是否连接成功？ | cshtml 标签 |
| `idcisitnormal` | 7.原始数据是否与数据采集到的数 据一致 | cshtml 标签 |
| `ircisitnormal` | 5.接收头是否进行清 理？（每周清理一次） | cshtml 标签 |
| `itnisitnormal` | 4.检查/更换干燥剂 | cshtml 标签 |
| `itsisitnormal` | 3.测量物种是否正确（JO1D、 JHCHO_M、JNO2、JH2O2、JHONO 、JNO3_M、JHCHO_R、JNO_R） | cshtml 标签 |
| `nsrisitnormal` | 6.夜间信号范围（-10E-4～10E- 4） | cshtml 标签 |
| `nstisitnormal` | 室内外 环境 / 1.监测站内温度(20～30℃) | cshtml 标签 |
| `wnmisitnormal` | 校准 / 1.是否进行暗噪声校准？（每月 做一次） | cshtml 标签 |
| `acstisitnormal` | 2.空调设置温度(18～26℃) | cshtml 标签 |
| `itaaisitnormal` | 4.查看历史数据是否有异常或者缺 失？ | cshtml 标签 |
| `itnsisitnormal` | 6.网络是否开正常？ | cshtml 标签 |


## Sup_RF_TSIFlowCheckRecord（sup_rf_common）
- 源码依据：实体 `Sup_RF_TSIFlowCheckRecord`、视图 `Sup_RF_TSIFlowCheckRecord.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次检定时间（视图标签：截距 / 相关系数） | 实体注释 |
| `time2` | 参考流量计 - 下一次检定时间（视图标签：截距 / 相关系数） | 实体注释 |
| `time3` | TSI设备信息 - 上一次核查时间（视图标签：上一次 / 下一次） | 实体注释 |
| `time4` | TSI设备信息 - 下一次核查时间（视图标签：上一次 / 下一次） | 实体注释 |
| `bool_1` | 核查结果情况（视图标签：核查结果情况：） | 实体注释 |
| `string1` | 设备型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string2` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string3` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string4` | 截距 | 实体注释 |
| `string5` | 相关系数 | 实体注释 |
| `string6` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string7` | 出厂编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string8` | 目标流量 - TSI-3321 | 实体注释 |
| `string9` | 实测流量（1） - TSI-3321 | 实体注释 |
| `string10` | 实测流量（2） - TSI-3321 | 实体注释 |
| `string11` | 实测流量（3） - TSI-3321 | 实体注释 |
| `string12` | 平均实测流量 - TSI-3321 | 实体注释 |
| `string13` | 偏差 - TSI-3321 | 实体注释 |
| `string14` | 备注 - TSI-3321 | 实体注释 |
| `string15` | 目标流量 - TSI-3775 | 实体注释 |
| `string16` | 实测流量（1） - TSI-3775 | 实体注释 |
| `string17` | 实测流量（2） - TSI-3775 | 实体注释 |
| `string18` | 实测流量（3） - TSI-3775 | 实体注释 |
| `string19` | 平均实测流量 - TSI-3775 | 实体注释 |
| `string20` | 偏差 - TSI-3775 | 实体注释 |
| `string21` | 备注 - TSI-3775 | 实体注释 |
| `string22` | 目标流量 - TSI-3776 | 实体注释 |
| `string23` | 实测流量（1） - TSI-3776 | 实体注释 |
| `string24` | 实测流量（2） - TSI-3776 | 实体注释 |
| `string25` | 实测流量（3） - TSI-3776 | 实体注释 |
| `string26` | 平均实测流量 - TSI-3776 | 实体注释 |
| `string27` | 偏差 - TSI-3776 | 实体注释 |
| `string28` | 备注 - TSI-3776 | 实体注释 |
| `tsibtime` | 上一次 / 下一次 | cshtml 标签 |
| `tsietime` | 上一次 / 下一次 | cshtml 标签 |
| `flowbtime` | 截距 / 相关系数 | cshtml 标签 |
| `flowetime` | 截距 / 相关系数 | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**Vue 头部字段映射（Sup_RF_TSIFlowCheckRecord_ParticleMeter-L_TSI.vue）：**

string1 至 string28 为原表文本字段；time1 至 time4 为核查日期； bool_1 为核查结果；remark 为总备注；commonFile 为附件。

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_TSIRoutineCheck（sup_rf_common）
- 源码依据：实体 `Sup_RF_TSIRoutineCheck`、视图 `Sup_RF_TSIRoutineCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 仪器状态 - TSI-3321（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_2` | 变色硅胶使用情况 - TSI-3321（视图标签：2 / 变色硅胶使用情况） | 实体注释 |
| `bool_3` | 采样管路检查 - TSI-3321（视图标签：3 / 采样管路检查） | 实体注释 |
| `bool_4` | 入口喷嘴检查 - TSI-3321（视图标签：4 / 入口喷嘴检查） | 实体注释 |
| `bool_5` | 出口喷嘴检查 - TSI-3321（视图标签：5 / 出口喷嘴检查） | 实体注释 |
| `bool_6` | 激光能量值检查 - TSI-3321（视图标签：6 / 激光能量值检查） | 实体注释 |
| `bool_7` | 变色硅胶 - TSI-3321（视图标签：1 / 变色硅胶） | 实体注释 |
| `bool_8` | 仪器状态 - TSI-3775（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_9` | 饱和蒸汽温度（39℃） - TSI-3775（视图标签：2 / 饱和蒸汽温度（39℃）） | 实体注释 |
| `bool_10` | 制冷温度（14℃） - TSI-3775（视图标签：3 / 制冷温度（14℃）） | 实体注释 |
| `bool_11` | 限流孔压力（未出现红色报警） - TSI-3775（视图标签：4 / 限流孔压力（未出现红色报警）） | 实体注释 |
| `bool_12` | 正丁醇余量（标注刻度线） - TSI-3775（视图标签：5 / 正丁醇余量（标注刻度线）） | 实体注释 |
| `bool_13` | 压力管路积液检查 - TSI-3775（视图标签：6 / 压力管路积液检查） | 实体注释 |
| `bool_14` | 采样泵工作状态 - TSI-3775（视图标签：7 / 采样泵工作状态） | 实体注释 |
| `bool_15` | 采样流量 - TSI-3775（视图标签：8 / 采样流量） | 实体注释 |
| `bool_16` | 变色硅胶 - TSI-3775（视图标签：1 / 变色硅胶） | 实体注释 |
| `bool_17` | 正丁醇 - TSI-3775（视图标签：2 / 正丁醇） | 实体注释 |
| `bool_18` | 仪器状态 - TSI-3776（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_19` | 饱和蒸汽温度（39℃） - TSI-3776（视图标签：2 / 饱和蒸汽温度（39℃）） | 实体注释 |
| `bool_20` | 制冷温度（10℃） - TSI-3776（视图标签：3 / 制冷温度（10℃）） | 实体注释 |
| `bool_21` | 限流孔压力（未出现红色报警） - TSI-3776（视图标签：4 / 限流孔压力（未出现红色报警）） | 实体注释 |
| `bool_22` | 正丁醇余量（标注刻度线） - TSI-3776（视图标签：5 / 正丁醇余量（标注刻度线）） | 实体注释 |
| `bool_23` | 压力管路积液检查 - TSI-3776（视图标签：6 / 压力管路积液检查） | 实体注释 |
| `bool_24` | 采样泵工作状态 - TSI-3776（视图标签：7 / 采样泵工作状态） | 实体注释 |
| `bool_25` | 采样流量 - TSI-3776（视图标签：8 / 采样流量） | 实体注释 |
| `bool_26` | 变色硅胶 - TSI-3776（视图标签：1 / 变色硅胶） | 实体注释 |
| `bool_27` | 正丁醇 - TSI-3776（视图标签：2 / 正丁醇） | 实体注释 |
| `string1` | 仪器状态 - TSI-3321（视图标签：1 / 仪器状态） | 实体注释 |
| `string2` | 变色硅胶使用情况 - TSI-3321（视图标签：2 / 变色硅胶使用情况） | 实体注释 |
| `string3` | 采样管路检查 - TSI-3321（视图标签：3 / 采样管路检查） | 实体注释 |
| `string4` | 入口喷嘴检查 - TSI-3321（视图标签：4 / 入口喷嘴检查） | 实体注释 |
| `string5` | 出口喷嘴检查 - TSI-3321（视图标签：5 / 出口喷嘴检查） | 实体注释 |
| `string6` | 激光能量值检查 - TSI-3321（视图标签：6 / 激光能量值检查） | 实体注释 |
| `string7` | 变色硅胶 - TSI-3321（视图标签：1 / 变色硅胶） | 实体注释 |
| `string8` | 仪器状态 - TSI-3775（视图标签：1 / 仪器状态） | 实体注释 |
| `string9` | 饱和蒸汽温度（39℃） - TSI-3775（视图标签：2 / 饱和蒸汽温度（39℃）） | 实体注释 |
| `string10` | 制冷温度（14℃） - TSI-3775（视图标签：3 / 制冷温度（14℃）） | 实体注释 |
| `string11` | 限流孔压力（未出现红色报警） - TSI-3775（视图标签：4 / 限流孔压力（未出现红色报警）） | 实体注释 |
| `string12` | 正丁醇余量（标注刻度线） - TSI-3775（视图标签：5 / 正丁醇余量（标注刻度线）） | 实体注释 |
| `string13` | 压力管路积液检查 - TSI-3775（视图标签：6 / 压力管路积液检查） | 实体注释 |
| `string14` | 采样泵工作状态 - TSI-3775（视图标签：7 / 采样泵工作状态） | 实体注释 |
| `string15` | 采样流量 - TSI-3775（视图标签：8 / 采样流量） | 实体注释 |
| `string16` | 变色硅胶 - TSI-3775（视图标签：1 / 变色硅胶） | 实体注释 |
| `string17` | 正丁醇 - TSI-3775（视图标签：2 / 正丁醇） | 实体注释 |
| `string18` | 仪器状态 - TSI-3776（视图标签：1 / 仪器状态） | 实体注释 |
| `string19` | 饱和蒸汽温度（39℃） - TSI-3776（视图标签：2 / 饱和蒸汽温度（39℃）） | 实体注释 |
| `string20` | 制冷温度（10℃） - TSI-3776（视图标签：3 / 制冷温度（10℃）） | 实体注释 |
| `string21` | 限流孔压力（未出现红色报警） - TSI-3776（视图标签：4 / 限流孔压力（未出现红色报警）） | 实体注释 |
| `string22` | 正丁醇余量（标注刻度线） - TSI-3776（视图标签：5 / 正丁醇余量（标注刻度线）） | 实体注释 |
| `string23` | 压力管路积液检查 - TSI-3776（视图标签：6 / 压力管路积液检查） | 实体注释 |
| `string24` | 采样泵工作状态 - TSI-3776（视图标签：7 / 采样泵工作状态） | 实体注释 |
| `string25` | 采样流量 - TSI-3776（视图标签：8 / 采样流量） | 实体注释 |
| `string26` | 变色硅胶 - TSI-3776（视图标签：1 / 变色硅胶） | 实体注释 |
| `string27` | 正丁醇 - TSI-3776（视图标签：2 / 正丁醇） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**Vue 头部字段映射（Sup_RF_TSIRoutineCheck_ParticleMeter-L_TSI.vue）：**

bool_1 至 bool_27、string1 至 string27 分别对应 27 项检查结果及备注； true 为正常/有效，false 为异常/更换；remark 为总备注；commonFile 为附件。


## Sup_RF_TurbidiMeterCalibration（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/浊度计.docx
- 源码依据：实体 `Sup_RF_TurbidiMeterCalibration`、视图 `Sup_RF_TurbidiMeterCalibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 仪器状态（视图标签：σ450） | 实体注释 |
| `bool_2` | 分子涡轮泵工作状态（视图标签：σ525） | 实体注释 |
| `bool_3` | 分子涡轮泵温度（视图标签：σ630） | 实体注释 |
| `bool_4` | 真空规状态（视图标签：σ450） | 实体注释 |
| `bool_5` | 低规三（2-2.3toor）（视图标签：σ525） | 实体注释 |
| `bool_6` | 电离激光冷却水液位（视图标签：σ630） | 实体注释 |
| `bool_7` | 电离激光能量值：0.5mJ | 实体注释 |
| `bool_8` | 采样泵工作状态 | 实体注释 |
| `bool_9` | 变色硅胶使用情况 | 实体注释 |
| `bool_10` | 电离图谱情况 | 实体注释 |
| `bool_11` | 源解析图谱检查 | 实体注释 |
| `bool_12` | 激光冷却水 | 实体注释 |
| `bool_13` | 干燥硅胶 | 实体注释 |
| `string1` | 仪器状态（视图标签：σ450） | 实体注释 |
| `string2` | 分子涡轮泵工作状态（视图标签：σ450） | 实体注释 |
| `string3` | 分子涡轮泵工作状态（视图标签：σ450） | 实体注释 |
| `string4` | 真空规状态（视图标签：σ450） | 实体注释 |
| `string5` | 低规三（2-2.3toor）（视图标签：σ525） | 实体注释 |
| `string6` | 电离激光冷却水液位（视图标签：σ525） | 实体注释 |
| `string7` | 电离激光能量值：0.5mJ（视图标签：σ525） | 实体注释 |
| `string8` | 采样泵工作状态（视图标签：σ525） | 实体注释 |
| `string9` | 变色硅胶使用情况（视图标签：σ630） | 实体注释 |
| `string10` | 电离图谱情况（视图标签：σ630） | 实体注释 |
| `string11` | 源解析图谱检查（视图标签：σ630） | 实体注释 |
| `string12` | 激光冷却水（视图标签：σ630） | 实体注释 |
| `string13` | 干燥硅胶（视图标签：σ450） | 实体注释 |
| `string14` | σ450 | cshtml 标签 |
| `string15` | σ450 | cshtml 标签 |
| `string16` | σ450 | cshtml 标签 |
| `string17` | σ525 | cshtml 标签 |
| `string18` | σ525 | cshtml 标签 |
| `string19` | σ525 | cshtml 标签 |
| `string20` | σ525 | cshtml 标签 |
| `string21` | σ630 | cshtml 标签 |
| `string22` | σ630 | cshtml 标签 |
| `string23` | σ630 | cshtml 标签 |
| `string24` | σ630 | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_TurbidiMeterRoutineCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/浊度计.docx
- 源码依据：实体 `Sup_RF_TurbidiMeterRoutineCheck`、视图 `Sup_RF_TurbidiMeterRoutineCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 仪器状态（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_2` | 仪器运行参数（视图标签：2 / 仪器运行参数） | 实体注释 |
| `bool_3` | 仪器运行时钟（视图标签：3 / 仪器运行时钟） | 实体注释 |
| `bool_4` | 采样风机运转情况（视图标签：4 / 采样风机运转情况） | 实体注释 |
| `bool_5` | 每月度维护检查（视图标签：采样风机运转情况 / 正常 异常） | 实体注释 |
| `bool_6` | 每年度维护检查（视图标签：采样风机运转情况 / 正常 异常） | 实体注释 |
| `bool_7` | 年度预防性维护检查 | 实体注释 |
| `bool_8` | 户外采样头清洁（视图标签：1 / 户外采样头清洁） | 实体注释 |
| `bool_9` | 测量室腔室清洁（视图标签：2 / 测量室腔室清洁） | 实体注释 |
| `bool_10` | 漏气检查（视图标签：1 / 漏气检查） | 实体注释 |
| `bool_11` | 零/标精细过滤器更换（视图标签：1 / 零/标精细过滤器更换） | 实体注释 |
| `bool_12` | 零/标粗过滤器更换（视图标签：2 / 零/标粗过滤器更换） | 实体注释 |
| `bool_13` | 气路（仪器内部和气压泵）清洗（视图标签：1 / 气路（仪器内部和气压泵）清洗） | 实体注释 |
| `bool_14` | 电池更换（视图标签：1 / 电池更换） | 实体注释 |
| `bool_15` | 标气（视图标签：2 / 标气） | 实体注释 |
| `string1` | 仪器状态（视图标签：1 / 仪器状态） | 实体注释 |
| `string2` | 仪器运行参数（视图标签：2 / 仪器运行参数） | 实体注释 |
| `string3` | 仪器运行时钟（视图标签：3 / 仪器运行时钟） | 实体注释 |
| `string4` | 采样风机运转情况（视图标签：4 / 采样风机运转情况） | 实体注释 |
| `string5` | 户外采样头清洁（视图标签：1 / 户外采样头清洁） | 实体注释 |
| `string6` | 测量室腔室清洁（视图标签：2 / 测量室腔室清洁） | 实体注释 |
| `string7` | 漏气检查（视图标签：1 / 漏气检查） | 实体注释 |
| `string8` | 零/标精细过滤器更换（视图标签：1 / 零/标精细过滤器更换） | 实体注释 |
| `string9` | 零/标粗过滤器更换（视图标签：2 / 零/标粗过滤器更换） | 实体注释 |
| `string10` | 气路（仪器内部和气压泵）清洗（视图标签：1 / 气路（仪器内部和气压泵）清洗） | 实体注释 |
| `string11` | 电池更换（视图标签：1 / 电池更换） | 实体注释 |
| `string12` | 标气（视图标签：2 / 标气） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_TurbidiMeterSamplingCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/浊度计.docx
- 源码依据：实体 `Sup_RF_TurbidiMeterSamplingCheck`、视图 `Sup_RF_TurbidiMeterSamplingCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 浊度计资料 - 上一次校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time2` | 浊度计资料 - 下一次校准日期（视图标签：上一次 / 下一次） | 实体注释 |
| `time3` | 参考流量计 - 上一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `time4` | 参考流量计 - 下一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `bool_1` | 是否在要求范围内（视图标签：2-5L/min） | 实体注释 |
| `string1` | 仪器型号（视图标签：上一次 / 下一次） | 实体注释 |
| `string2` | 出厂编号（视图标签：上一次 / 下一次） | 实体注释 |
| `string3` | 监测项目（视图标签：上一次 / 下一次） | 实体注释 |
| `string4` | 设备/流量计型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string5` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string7` | 截距（视图标签：截距 / 相关系数） | 实体注释 |
| `string8` | 相关系数 | 实体注释 |
| `string9` | 直接读取的标准读数（视图标签：2-5L/min） | 实体注释 |
| `string10` | 已修正的标准值（视图标签：2-5L/min） | 实体注释 |
| `string11` | 偏差（％）（视图标签：2-5L/min） | 实体注释 |
| `string27` | 备注： | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required,double；`string11`=required,double；`string2`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required,double


## Sup_RF_Turbidimeter_HalfYear（sup_rf_turbidimeter）
- 《组分仪器工单规则》：颗粒物组分/浊度计.docx
- 源码依据：实体 `Sup_RF_Turbidimeter`、视图 `Sup_RF_Turbidimeter.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `formtype` | 表单类型 周 月 季 半年 | 实体注释 |
| `lsremarks` | 光源 / 检查/校准 | cshtml 标签 |
| `mcremarks` | 测量室腔 / 检查/清洁 | cshtml 标签 |
| `sgremarks` | 标气 / 检查/更换 | cshtml 标签 |
| `capremarks` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `gasremarks` | 气路 / 检查/清洁 | cshtml 标签 |
| `standardgas` | 巡查项目 / 本次值 / 差值 / 参考值/方法 | cshtml 标签 |
| `sureremarks` | 测量室 / 检查/清洁 | cshtml 标签 |
| `clockremarks` | 时钟调整 / 检查/校准 | cshtml 标签 |
| `lsisitnormal` | 光源 / 检查/校准 | cshtml 标签 |
| `mcisitnormal` | 测量室腔 / 检查/清洁 | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `sgisitnormal` | 标气 / 检查/更换 | cshtml 标签 |
| `capisitnormal` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `gasisitnormal` | 气路 / 检查/清洁 | cshtml 标签 |
| `batteryremarks` | 电池 / 检查/更换 | cshtml 标签 |
| `cfilterremarks` | 粗过滤器 / 检查/更换 | cshtml 标签 |
| `ffilterremarks` | 细过滤器 / 检查/更换 | cshtml 标签 |
| `sureisitnormal` | 测量室 / 检查/清洁 | cshtml 标签 |
| `clockisitnormal` | 时钟调整 / 检查/校准 | cshtml 标签 |
| `sp450difference` | 450nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp525difference` | 525nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp635difference` | 跨度 / 635nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `zp450difference` | 450nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp525difference` | 525nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp635difference` | 零点 / 635nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `batteryisitnormal` | 电池 / 检查/更换 | cshtml 标签 |
| `cfilterisitnormal` | 粗过滤器 / 检查/更换 | cshtml 标签 |
| `ffilterisitnormal` | 细过滤器 / 检查/更换 | cshtml 标签 |
| `sp450currentvalue` | 450nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp525currentvalue` | 525nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp635currentvalue` | 跨度 / 635nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `zp450currentvalue` | 450nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp525currentvalue` | 525nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp635currentvalue` | 零点 / 635nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |


## Sup_RF_Turbidimeter_Month（sup_rf_turbidimeter）
- 《组分仪器工单规则》：颗粒物组分/浊度计.docx
- 源码依据：实体 `Sup_RF_Turbidimeter`、视图 `Sup_RF_Turbidimeter.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `formtype` | 表单类型 周 月 季 半年 | 实体注释 |
| `lsremarks` | 光源 / 检查/校准 | cshtml 标签 |
| `mcremarks` | 测量室腔 / 检查/清洁 | cshtml 标签 |
| `sgremarks` | 标气 / 检查/更换 | cshtml 标签 |
| `capremarks` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `gasremarks` | 气路 / 检查/清洁 | cshtml 标签 |
| `standardgas` | 巡查项目 / 本次值 / 差值 / 参考值/方法 | cshtml 标签 |
| `sureremarks` | 测量室 / 检查/清洁 | cshtml 标签 |
| `clockremarks` | 时钟调整 / 检查/校准 | cshtml 标签 |
| `lsisitnormal` | 光源 / 检查/校准 | cshtml 标签 |
| `mcisitnormal` | 测量室腔 / 检查/清洁 | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `sgisitnormal` | 标气 / 检查/更换 | cshtml 标签 |
| `capisitnormal` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `gasisitnormal` | 气路 / 检查/清洁 | cshtml 标签 |
| `batteryremarks` | 电池 / 检查/更换 | cshtml 标签 |
| `cfilterremarks` | 粗过滤器 / 检查/更换 | cshtml 标签 |
| `ffilterremarks` | 细过滤器 / 检查/更换 | cshtml 标签 |
| `sureisitnormal` | 测量室 / 检查/清洁 | cshtml 标签 |
| `clockisitnormal` | 时钟调整 / 检查/校准 | cshtml 标签 |
| `sp450difference` | 450nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp525difference` | 525nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp635difference` | 跨度 / 635nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `zp450difference` | 450nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp525difference` | 525nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp635difference` | 零点 / 635nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `batteryisitnormal` | 电池 / 检查/更换 | cshtml 标签 |
| `cfilterisitnormal` | 粗过滤器 / 检查/更换 | cshtml 标签 |
| `ffilterisitnormal` | 细过滤器 / 检查/更换 | cshtml 标签 |
| `sp450currentvalue` | 450nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp525currentvalue` | 525nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp635currentvalue` | 跨度 / 635nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `zp450currentvalue` | 450nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp525currentvalue` | 525nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp635currentvalue` | 零点 / 635nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |


## Sup_RF_Turbidimeter_Quarter（sup_rf_turbidimeter）
- 《组分仪器工单规则》：颗粒物组分/浊度计.docx
- 源码依据：实体 `Sup_RF_Turbidimeter`、视图 `Sup_RF_Turbidimeter.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `formtype` | 表单类型 周 月 季 半年 | 实体注释 |
| `lsremarks` | 光源 / 检查/校准 | cshtml 标签 |
| `mcremarks` | 测量室腔 / 检查/清洁 | cshtml 标签 |
| `sgremarks` | 标气 / 检查/更换 | cshtml 标签 |
| `capremarks` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `gasremarks` | 气路 / 检查/清洁 | cshtml 标签 |
| `standardgas` | 巡查项目 / 本次值 / 差值 / 参考值/方法 | cshtml 标签 |
| `sureremarks` | 测量室 / 检查/清洁 | cshtml 标签 |
| `clockremarks` | 时钟调整 / 检查/校准 | cshtml 标签 |
| `lsisitnormal` | 光源 / 检查/校准 | cshtml 标签 |
| `mcisitnormal` | 测量室腔 / 检查/清洁 | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `sgisitnormal` | 标气 / 检查/更换 | cshtml 标签 |
| `capisitnormal` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `gasisitnormal` | 气路 / 检查/清洁 | cshtml 标签 |
| `batteryremarks` | 电池 / 检查/更换 | cshtml 标签 |
| `cfilterremarks` | 粗过滤器 / 检查/更换 | cshtml 标签 |
| `ffilterremarks` | 细过滤器 / 检查/更换 | cshtml 标签 |
| `sureisitnormal` | 测量室 / 检查/清洁 | cshtml 标签 |
| `clockisitnormal` | 时钟调整 / 检查/校准 | cshtml 标签 |
| `sp450difference` | 450nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp525difference` | 525nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp635difference` | 跨度 / 635nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `zp450difference` | 450nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp525difference` | 525nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp635difference` | 零点 / 635nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `batteryisitnormal` | 电池 / 检查/更换 | cshtml 标签 |
| `cfilterisitnormal` | 粗过滤器 / 检查/更换 | cshtml 标签 |
| `ffilterisitnormal` | 细过滤器 / 检查/更换 | cshtml 标签 |
| `sp450currentvalue` | 450nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp525currentvalue` | 525nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp635currentvalue` | 跨度 / 635nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `zp450currentvalue` | 450nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp525currentvalue` | 525nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp635currentvalue` | 零点 / 635nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |


## Sup_RF_Turbidimeter_Week（sup_rf_turbidimeter）
- 《组分仪器工单规则》：颗粒物组分/浊度计.docx
- 源码依据：实体 `Sup_RF_Turbidimeter`、视图 `Sup_RF_Turbidimeter.cshtml`、Vue 移植版 x4

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `formtype` | 表单类型 周 月 季 半年 | 实体注释 |
| `lsremarks` | 光源 / 检查/校准 | cshtml 标签 |
| `mcremarks` | 测量室腔 / 检查/清洁 | cshtml 标签 |
| `sgremarks` | 标气 / 检查/更换 | cshtml 标签 |
| `capremarks` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `gasremarks` | 气路 / 检查/清洁 | cshtml 标签 |
| `standardgas` | 巡查项目 / 本次值 / 差值 / 参考值/方法 | cshtml 标签 |
| `sureremarks` | 测量室 / 检查/清洁 | cshtml 标签 |
| `clockremarks` | 时钟调整 / 检查/校准 | cshtml 标签 |
| `lsisitnormal` | 光源 / 检查/校准 | cshtml 标签 |
| `mcisitnormal` | 测量室腔 / 检查/清洁 | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `sgisitnormal` | 标气 / 检查/更换 | cshtml 标签 |
| `capisitnormal` | 防虫雨帽 / 检查/清洁 | cshtml 标签 |
| `gasisitnormal` | 气路 / 检查/清洁 | cshtml 标签 |
| `batteryremarks` | 电池 / 检查/更换 | cshtml 标签 |
| `cfilterremarks` | 粗过滤器 / 检查/更换 | cshtml 标签 |
| `ffilterremarks` | 细过滤器 / 检查/更换 | cshtml 标签 |
| `sureisitnormal` | 测量室 / 检查/清洁 | cshtml 标签 |
| `clockisitnormal` | 时钟调整 / 检查/校准 | cshtml 标签 |
| `sp450difference` | 450nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp525difference` | 525nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp635difference` | 跨度 / 635nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `zp450difference` | 450nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp525difference` | 525nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp635difference` | 零点 / 635nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `batteryisitnormal` | 电池 / 检查/更换 | cshtml 标签 |
| `cfilterisitnormal` | 粗过滤器 / 检查/更换 | cshtml 标签 |
| `ffilterisitnormal` | 细过滤器 / 检查/更换 | cshtml 标签 |
| `sp450currentvalue` | 450nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp525currentvalue` | 525nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `sp635currentvalue` | 跨度 / 635nm / ±10%{差值=（本-标）/标*100%} | cshtml 标签 |
| `zp450currentvalue` | 450nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp525currentvalue` | 525nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `zp635currentvalue` | 零点 / 635nm / 0 / ±2Mm-1（差值=本-标） | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_Turbidimeter_HalfYear_NepheloMeter_EC.vue）：**

bool_1 至 bool_3 为电池、气路、测量室腔结果（true = 正常，false = 异常）； remark、remark1、remark2 为对应备注；remark3 为其他；commonFile 为附件。

**Vue 头部字段映射（Sup_RF_Turbidimeter_Quarter_NepheloMeter_EC.vue）：**

bool_1 至 bool_3 为时钟调整、防虫雨帽、测量室结果（true = 正常，false = 异常）； remark、remark1、remark2 为对应备注；remark3 为其他；commonFile 为附件。


## Sup_RF_URGMonthMaintain（sup_rf_urgmonthmaintain）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_URGMonthMaintain`、视图 `Sup_RF_URGMonthMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `iconeresult` | 3 / IC单向阀清洁 | cshtml 标签 |
| `icsixresult` | 2 / IC六通阀阀芯清洁 | cshtml 标签 |
| `iconeremarks` | 3 / IC单向阀清洁 | cshtml 标签 |
| `icsixremarks` | 2 / IC六通阀阀芯清洁 | cshtml 标签 |
| `denuderresult` | 4 / 清洗DENUDER | cshtml 标签 |
| `denuderremarks` | 4 / 清洗DENUDER | cshtml 标签 |
| `cleaningcuttingheadresult` | 1 / AERSOL清洗切割头 | cshtml 标签 |
| `cleaningcuttingheadremarks` | 1 / AERSOL清洗切割头 | cshtml 标签 |


## Sup_RF_URGQuarterMaintain（sup_rf_urgquartermaintain）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_URGQuarterMaintain`、视图 `Sup_RF_URGQuarterMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `iconeresult` | 4 / IC定量环清洗 | cshtml 标签 |
| `iconeremarks` | 4 / IC定量环清洗 | cshtml 标签 |
| `cleaningresult` | 1 / 清洗溶蚀器、蒸汽发生器及前处理内部管路 | cshtml 标签 |
| `cleaningremarks` | 1 / 清洗溶蚀器、蒸汽发生器及前处理内部管路 | cshtml 标签 |
| `wastecollectorresult` | 2 / 废液收集器清洗 | cshtml 标签 |
| `wastecollectorremarks` | 2 / 废液收集器清洗 | cshtml 标签 |
| `condensingcollectorresult` | 5 / 冷凝收集器清洗 | cshtml 标签 |
| `condensingcollectorremarks` | 5 / 冷凝收集器清洗 | cshtml 标签 |
| `inspectionofvacuumpumpresult` | 3 / 真空泵检查 | cshtml 标签 |
| `inspectionofvacuumpumpremarks` | 3 / 真空泵检查 | cshtml 标签 |


## Sup_RF_URGWeekMaintain（sup_rf_urgweekmaintain）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_URGWeekMaintain`、视图 `Sup_RF_URGWeekMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `anionicwaterpeak1` | 9 / 阴离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `anionicwaterpeak2` | 9 / 阴离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `anionanalyzerresult` | 1 / 阴离子分析仪运行参数 | cshtml 标签 |
| `anionflowrateresult` | 8 / 阴离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `anionpressureresult` | 7 / 阴离子柱压（2mm：1500-2500psi） | cshtml 标签 |
| `syringestatusresult` | 4 / 注射器状态 | cshtml 标签 |
| `anionanalyzerremarks` | 1 / 阴离子分析仪运行参数 | cshtml 标签 |
| `anionflowrateremarks` | 8 / 阴离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `anionpressureremarks` | 7 / 阴离子柱压（2mm：1500-2500psi） | cshtml 标签 |
| `cationanalyzerresult` | 2 / 阳离子分析仪运行参数 | cshtml 标签 |
| `cationflowrateresult` | 6 / 阳离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `cationpressureresult` | 5 / 阳离子柱压（2mm：1500-2500psi） | cshtml 标签 |
| `chromatographyresult` | 4 / 阴阳离子色谱基线状态 | cshtml 标签 |
| `steamgeneratorresult` | 5 / 蒸汽发生器水位 | cshtml 标签 |
| `syringestatusremarks` | 4 / 注射器状态 | cshtml 标签 |
| `cationanalyzerremarks` | 2 / 阳离子分析仪运行参数 | cshtml 标签 |
| `cationflowrateremarks` | 6 / 阳离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `cationpressureremarks` | 5 / 阳离子柱压（2mm：1500-2500psi） | cshtml 标签 |
| `chromatographyremarks` | 4 / 阴阳离子色谱基线状态 | cshtml 标签 |
| `steamgeneratorremarks` | 5 / 蒸汽发生器水位 | cshtml 标签 |
| `instrumentstatusresult` | 1 / 仪器状态 | cshtml 标签 |
| `anionicwaterpeakremarks` | 9 / 阴离子柱流量（2mm：0.2-0.3ml/min） | cshtml 标签 |
| `chameleonsoftwareresult` | 3 / 变色龙软件运行状态 | cshtml 标签 |
| `instrumentstatusremarks` | 1 / 仪器状态 | cshtml 标签 |
| `chameleonsoftwareremarks` | 3 / 变色龙软件运行状态 | cshtml 标签 |
| `wasteliquidemptyingresult` | 10 / 废液清空 | cshtml 标签 |
| `wasteliquidemptyingremarks` | 10 / 废液清空 | cshtml 标签 |
| `samplingpumpinspectionresult` | 2 / 采样泵检查 | cshtml 标签 |
| `samplingpumpinspectionremarks` | 2 / 采样泵检查 | cshtml 标签 |
| `peristalticpumpinspectionresult` | 3 / 排废液蠕动泵检查 | cshtml 标签 |
| `peristalticpumpinspectionremarks` | 3 / 排废液蠕动泵检查 | cshtml 标签 |


## Sup_RF_URGYearMaintain（sup_rf_urgyearmaintain）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_URGYearMaintain`、视图 `Sup_RF_URGYearMaintain.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `anioncolumnresult` | 8 / 阴离子分析柱、保护柱 / 每半年至少更换1次 | cshtml 标签 |
| `inlinefilterresult` | 12 / Inline Filter膜片 | cshtml 标签 |
| `anioniceeluentresult` | 1 / 阴离子淋洗液（氢氧化钾） / 液位低于容积的1/5应及时整瓶更换。每次更换淋洗液 后应通过单点核查的方式检查目标物的保留时间 和背景电导率，看保留时间漂移情况，如漂移 超出0.5min， 应重新更换淋洗液。 | cshtml 标签 |
| `cationiccolumnresult` | 9 / 阳离子分析柱、保护柱 | cshtml 标签 |
| `cationiceluentresult` | 2 / 阳离子淋洗液（甲磺酸） | cshtml 标签 |
| `ultrapurewaterresult` | 4 / 超纯水 | cshtml 标签 |
| `anionprotectionresult` | 6 / 阴阳离子保护柱垫片更换 | cshtml 标签 |
| `cleaningsamplingresult` | 1 / 采样管清洁 | cshtml 标签 |
| `icsystemcleaningresult` | 2 / IC全系统清洁 | cshtml 标签 |
| `aerosolfilterheadresult` | 5 / 气溶胶过滤头 / 每两周至少更换1次，新滤头使用前需进行活化。 | cshtml 标签 |
| `cleaningsamplingremarks` | 1 / 采样管清洁 | cshtml 标签 |
| `icsystemcleaningremarks` | 2 / IC全系统清洁 | cshtml 标签 |
| `absorptionsolutionresult` | 3 / 吸收液（H2O2） | cshtml 标签 |
| `cationicprotectionresult` | 7 / 阴阳离子分析柱垫片更换 | cshtml 标签 |
| `samplingpumpfilterresult` | 10 / 采样泵过滤器 | cshtml 标签 |
| `peristalticpumppiperesult` | 11 / 蠕动泵管 | cshtml 标签 |
| `wholesystemcleaningresult` | 3 / 前处理全系统清洁 | cshtml 标签 |
| `wholesystemcleaningremarks` | 3 / 前处理全系统清洁 | cshtml 标签 |


## Sup_RF_VOCsAMASamplingFlowRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VOCsAMASamplingFlowRecord`、视图 `Sup_RF_VOCsAMASamplingFlowRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 上一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `time2` | 下一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `string1` | 设备编码 - 高碳（视图标签：仪器编码 / 高碳： / 温度（℃）） | 实体注释 |
| `string2` | 温度（视图标签：仪器编码 / 高碳： / 温度（℃）） | 实体注释 |
| `string3` | 设备编码 - 低碳（视图标签：低碳： / 湿度（%RH）） | 实体注释 |
| `string4` | 湿度（视图标签：低碳： / 湿度（%RH）） | 实体注释 |
| `string5` | 设备型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string7` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string8` | 截距（视图标签：截距 / 相关系数） | 实体注释 |
| `string9` | 相关系数 | 实体注释 |
| `string10` | 仪器流量 - 高碳 | 实体注释 |
| `string11` | 标准流量计 - 高碳 | 实体注释 |
| `string12` | 样气温度 - 高碳 | 实体注释 |
| `string13` | 样气压力 - 高碳 | 实体注释 |
| `string14` | 标准流量计修正 - 高碳 | 实体注释 |
| `string15` | 标准流量计标态 - 高碳 | 实体注释 |
| `string16` | 样气压力 - 高碳 | 实体注释 |
| `string17` | 偏差 - 高碳 | 实体注释 |
| `string18` | 仪器流量 - 低碳 | 实体注释 |
| `string19` | 标准流量计 - 低碳 | 实体注释 |
| `string20` | 样气温度 - 低碳 | 实体注释 |
| `string21` | 样气压力 - 低碳 | 实体注释 |
| `string22` | 标准流量计修正 - 低碳 | 实体注释 |
| `string23` | 标准流量计标态 - 低碳 | 实体注释 |
| `string24` | 样气压力 - 低碳 | 实体注释 |
| `string25` | 偏差 - 低碳 | 实体注释 |
| `string27` | 备注： | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required,double；`string11`=required,double；`string12`=required,double；`string13`=required,double；`string14`=required,double；`string15`=required,double；`string16`=required,double；`string17`=required,double；`string18`=required,double；`string19`=required,double；`string2`=required；`string20`=required,double；`string21`=required,double；`string22`=required,double；`string23`=required,double；`string24`=required,double；`string25`=required,double；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_VOCsChromatotecSamplingFlowRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VOCsChromatotecSamplingFlowRecord`、视图 `Sup_RF_VOCsChromatotecSamplingFlowRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 分析仪资料 - 上一次校准日期（视图标签：C2-C6：） | 实体注释 |
| `time2` | 分析仪资料 - 下一次校准日期（视图标签：C2-C6：） | 实体注释 |
| `time3` | 参考流量计 - 上一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `time4` | 参考流量计 - 下一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `string1` | 仪器型号（视图标签：C2-C6：） | 实体注释 |
| `string2` | 出厂编号 - C2-C6： | 实体注释 |
| `string3` | 监测项目（视图标签：C2-C6：） | 实体注释 |
| `string4` | 出厂编号 - C6-C12（视图标签：C6-C12:） | 实体注释 |
| `string5` | 设备/流量计型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string7` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string8` | 截距（视图标签：截距 / 相关系数） | 实体注释 |
| `string9` | 相关系数 | 实体注释 |
| `string10` | 现场温度(℃)（视图标签：现场温度 (℃) / 现场大气压(mmHg)） | 实体注释 |
| `string11` | 仪器设定值 - C2-C6 | 实体注释 |
| `string12` | 直接读取的标准读数 - C2-C6 | 实体注释 |
| `string13` | 已修正的标准值 - C2-C6 | 实体注释 |
| `string14` | 偏差（％ - C2-C6 | 实体注释 |
| `string15` | 核查结果 - C2-C6 | 实体注释 |
| `string16` | 仪器设定值 - C6-C12 | 实体注释 |
| `string17` | 直接读取的标准读数 - C6-C12 | 实体注释 |
| `string18` | 已修正的标准值 - C6-C12 | 实体注释 |
| `string19` | 偏差（％）- C6-C12 | 实体注释 |
| `string20` | 核查结果 - C6-C12 | 实体注释 |
| `string27` | 备注： | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required,double；`string12`=required,double；`string13`=required,double；`string14`=required,double；`string15`=required；`string16`=required,double；`string17`=required,double；`string18`=required,double；`string19`=required,double；`string2`=required；`string20`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_VOCsEXPECMulityPointCurveRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VOCsEXPECMulityPointCurveRecord`、视图 `Sup_RF_VOCsEXPECMulityPointCurveRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 核查结果情况 | 实体注释 |
| `string1` |  | 实体注释 |
| `string2` |  | 实体注释 |
| `string3` |  | 实体注释 |
| `string4` |  | 实体注释 |
| `string5` |  | 实体注释 |
| `string6` |  | 实体注释 |
| `string7` |  | 实体注释 |
| `string8` |  | 实体注释 |
| `string9` |  | 实体注释 |
| `string10` |  | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string13` |  | 实体注释 |
| `string14` |  | 实体注释 |
| `string15` |  | 实体注释 |
| `string16` |  | 实体注释 |
| `string17` |  | 实体注释 |
| `string18` |  | 实体注释 |
| `string19` |  | 实体注释 |
| `string20` |  | 实体注释 |
| `string21` |  | 实体注释 |
| `string22` |  | 实体注释 |
| `string23` |  | 实体注释 |
| `string24` |  | 实体注释 |
| `string25` |  | 实体注释 |
| `string26` |  | 实体注释 |
| `string27` |  | 实体注释 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_VOCsEXPECSamplingFlowRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VOCsEXPECSamplingFlowRecord`、视图 `Sup_RF_VOCsEXPECSamplingFlowRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 上一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `time2` | 下一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `string1` | 仪器编码 - 高碳（视图标签：仪器编码 / 高碳： / 温度（℃）） | 实体注释 |
| `string2` | 仪器编码 - 低碳（视图标签：仪器编码 / 高碳： / 温度（℃）） | 实体注释 |
| `string3` | 温度（视图标签：低碳： / 湿度（%RH）） | 实体注释 |
| `string4` | 湿度（视图标签：低碳： / 湿度（%RH）） | 实体注释 |
| `string5` | 设备型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string7` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string8` | 截距（视图标签：截距 / 相关系数） | 实体注释 |
| `string9` | 相关系数 | 实体注释 |
| `string10` | 仪器流量 - 高碳 | 实体注释 |
| `string11` | 标准流量计 - 高碳 | 实体注释 |
| `string12` | 标准流量计修正 - 高碳 | 实体注释 |
| `string13` | 偏差 - 高碳 | 实体注释 |
| `string14` | 仪器流量 - 低碳 | 实体注释 |
| `string15` | 标准流量计 - 低碳 | 实体注释 |
| `string16` | 标准流量计修正 - 低碳 | 实体注释 |
| `string17` | 偏差 - 低碳 | 实体注释 |
| `string27` | 备注： | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required,double；`string11`=required,double；`string12`=required,double；`string13`=required,double；`string14`=required,double；`string15`=required,double；`string16`=required,double；`string17`=required,double；`string2`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_VOCsMulityPointCurveRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VOCsMulityPointCurveRecord`、视图 `Sup_RF_VOCsMulityPointCurveRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 核查结果情况-AMA | 实体注释 |
| `bool_2` | 核查结果情况-武汉天虹 | 实体注释 |
| `string1` |  | 实体注释 |
| `string2` |  | 实体注释 |
| `string3` |  | 实体注释 |
| `string4` |  | 实体注释 |
| `string5` |  | 实体注释 |
| `string6` |  | 实体注释 |
| `string7` |  | 实体注释 |
| `string8` |  | 实体注释 |
| `string9` |  | 实体注释 |
| `string10` |  | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string13` |  | 实体注释 |
| `string14` |  | 实体注释 |
| `string15` |  | 实体注释 |
| `string16` |  | 实体注释 |
| `string17` |  | 实体注释 |
| `string18` |  | 实体注释 |
| `string19` |  | 实体注释 |
| `string20` |  | 实体注释 |
| `string21` |  | 实体注释 |
| `string22` |  | 实体注释 |
| `string23` |  | 实体注释 |
| `string24` |  | 实体注释 |
| `string25` |  | 实体注释 |
| `string26` |  | 实体注释 |
| `string27` |  | 实体注释 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_VOCsSinglePointCheckQC（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VOCsSinglePointCheckQC`、视图 `Sup_RF_VOCsSinglePointCheckQC.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：开始时间： / 结束时间：） | 实体注释 |
| `time2` | 结束时间（视图标签：开始时间： / 结束时间：） | 实体注释 |
| `bool_1` | 核查结果情况 | 实体注释 |
| `string1` |  | 实体注释 |
| `string2` |  | 实体注释 |
| `string3` |  | 实体注释 |
| `string4` |  | 实体注释 |
| `string5` |  | 实体注释 |
| `string6` |  | 实体注释 |
| `string7` |  | 实体注释 |
| `string8` |  | 实体注释 |
| `string9` |  | 实体注释 |
| `string10` |  | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string13` |  | 实体注释 |
| `string14` |  | 实体注释 |
| `string15` |  | 实体注释 |
| `string16` |  | 实体注释 |
| `string17` |  | 实体注释 |
| `string18` |  | 实体注释 |
| `string19` |  | 实体注释 |
| `string20` |  | 实体注释 |
| `string21` |  | 实体注释 |
| `string22` |  | 实体注释 |
| `string23` |  | 实体注释 |
| `string24` |  | 实体注释 |
| `string25` |  | 实体注释 |
| `string26` |  | 实体注释 |
| `string27` |  | 实体注释 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_VOCsWHTHMulityPointCurveRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VOCsWHTHMulityPointCurveRecord`、视图 `Sup_RF_VOCsWHTHMulityPointCurveRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 核查结果情况 | 实体注释 |
| `string1` |  | 实体注释 |
| `string2` |  | 实体注释 |
| `string3` |  | 实体注释 |
| `string4` |  | 实体注释 |
| `string5` |  | 实体注释 |
| `string6` |  | 实体注释 |
| `string7` |  | 实体注释 |
| `string8` |  | 实体注释 |
| `string9` |  | 实体注释 |
| `string10` |  | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string13` |  | 实体注释 |
| `string14` |  | 实体注释 |
| `string15` |  | 实体注释 |
| `string16` |  | 实体注释 |
| `string17` |  | 实体注释 |
| `string18` |  | 实体注释 |
| `string19` |  | 实体注释 |
| `string20` |  | 实体注释 |
| `string21` |  | 实体注释 |
| `string22` |  | 实体注释 |
| `string23` |  | 实体注释 |
| `string24` |  | 实体注释 |
| `string25` |  | 实体注释 |
| `string26` |  | 实体注释 |
| `string27` |  | 实体注释 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_VOCsWHTHSamplingFlowRecord（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VOCsWHTHSamplingFlowRecord`、视图 `Sup_RF_VOCsWHTHSamplingFlowRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 上一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `time2` | 下一次校准时间（视图标签：截距 / 相关系数） | 实体注释 |
| `bool_1` | FID流量检查 - 认证结果 | 实体注释 |
| `bool_2` | MS流量检查结果 - 认证结果 | 实体注释 |
| `string1` | 位置/楼层（视图标签：位置/楼层 / 温度（℃）） | 实体注释 |
| `string2` | 温度（视图标签：位置/楼层 / 温度（℃）） | 实体注释 |
| `string3` | 气压（视图标签：气压 / hpa / 湿度（%RH）） | 实体注释 |
| `string4` | 湿度（视图标签：气压 / hpa / 湿度（%RH）） | 实体注释 |
| `string5` | 设备型号（视图标签：截距 / 相关系数） | 实体注释 |
| `string6` | 出厂编号（视图标签：截距 / 相关系数） | 实体注释 |
| `string7` | 斜率（视图标签：截距 / 相关系数） | 实体注释 |
| `string8` | 截距（视图标签：截距 / 相关系数） | 实体注释 |
| `string9` | 相关系数 | 实体注释 |
| `string10` | FID流量检查结果 - 分析仪目标值（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string11` | FID流量检查结果 - 分析仪显示值（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string12` | FID流量检查结果 - 参考流量计读数（现场环境）（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string13` | FID流量检查结果 - 参考流量计根据方程修正值（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string14` | FID流量检查结果 - 参考流量计读数（标准状态*）（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string15` | FID流量检查结果 - 偏差（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string16` | FID流量检查结果 - 现场温度 | 实体注释 |
| `string17` | FID流量检查结果 - 现场大气压 | 实体注释 |
| `string18` | MS流量检查结果 - 分析仪目标值（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string19` | MS流量检查结果 - 分析仪显示值（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string20` | MS流量检查结果 - 参考流量计读数（现场环境）（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string21` | MS流量检查结果 - 参考流量计根据方程修正值（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string22` | MS流量检查结果 - 参考流量计读数（标准状态*）（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string23` | MS流量检查结果 - 偏差（视图标签：现场温度 （℃） / 现场大气压 （mmHg）） | 实体注释 |
| `string24` | MS流量检查结果 - 现场温度 | 实体注释 |
| `string25` | MS流量检查结果 - 现场大气压 | 实体注释 |
| `string27` | 备注： | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required,double；`string11`=required,double；`string12`=required,double；`string13`=required,double；`string14`=required,double；`string15`=required,double；`string16`=required,double；`string17`=required,double；`string18`=required,double；`string19`=required,double；`string2`=required；`string20`=required,double；`string21`=required,double；`string22`=required,double；`string23`=required,double；`string24`=required,double；`string25`=required,double；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_VisibilityMeter_HalfYear（sup_rf_visibilitymeter）
- 《组分仪器工单规则》：（能见度，RAR 外）
- 源码依据：实体 `Sup_RF_VisibilityMeter`、视图 `Sup_RF_VisibilityMeter.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `dtisit` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `davalue` | 偏差≤10% | cshtml 标签 |
| `optisit` | 光学部件 / 检查/清洁 / 季度 | cshtml 标签 |
| `surisit` | 仪器表面 / 检查/清洁 | cshtml 标签 |
| `weaisit` | 气象杆 / 检查 | cshtml 标签 |
| `zdvalue` | 偏差≤10% | cshtml 标签 |
| `formtype` | 表单类型 周 季 半年 | 实体注释 |
| `cableisit` | 电缆 / 检查 | cshtml 标签 |
| `dtremarks` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `aftervalue` | 偏差≤10% | cshtml 标签 |
| `optremarks` | 光学部件 / 检查/清洁 / 季度 | cshtml 标签 |
| `surremarks` | 仪器表面 / 检查/清洁 | cshtml 标签 |
| `wearemarks` | 气象杆 / 检查 | cshtml 标签 |
| `cableremarks` | 电缆 / 检查 | cshtml 标签 |
| `calibrationr` | 校准 / 标定值 / 零偏差值 / 校准后消光系数 / 校准后偏差 / 校准 / 半年 | cshtml 标签 |
| `calibremarks` | 偏差≤10% | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `calibrationvalue` | 偏差≤10% | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_VisibilityMeter_HalfYear_VisibilityMeter.vue）：**

string1 至 string4 分别为标定值、零偏差值、校准后消光系数、校准后偏差； remark 为校准备注，remark1 为偏差备注，remark2 为其他备注。 原表没有计算、自动判定、必填、格式校验或附件逻辑。


## Sup_RF_VisibilityMeter_Week（sup_rf_visibilitymeter）
- 《组分仪器工单规则》：（能见度，RAR 外）
- 源码依据：实体 `Sup_RF_VisibilityMeter`、视图 `Sup_RF_VisibilityMeter.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `dtisit` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `davalue` | 偏差≤10% | cshtml 标签 |
| `optisit` | 光学部件 / 检查/清洁 / 季度 | cshtml 标签 |
| `surisit` | 仪器表面 / 检查/清洁 | cshtml 标签 |
| `weaisit` | 气象杆 / 检查 | cshtml 标签 |
| `zdvalue` | 偏差≤10% | cshtml 标签 |
| `formtype` | 表单类型 周 季 半年 | 实体注释 |
| `cableisit` | 电缆 / 检查 | cshtml 标签 |
| `dtremarks` | 数据传输 / 检查 / 每周 | cshtml 标签 |
| `aftervalue` | 偏差≤10% | cshtml 标签 |
| `optremarks` | 光学部件 / 检查/清洁 / 季度 | cshtml 标签 |
| `surremarks` | 仪器表面 / 检查/清洁 | cshtml 标签 |
| `wearemarks` | 气象杆 / 检查 | cshtml 标签 |
| `cableremarks` | 电缆 / 检查 | cshtml 标签 |
| `calibrationr` | 校准 / 标定值 / 零偏差值 / 校准后消光系数 / 校准后偏差 / 校准 / 半年 | cshtml 标签 |
| `calibremarks` | 偏差≤10% | cshtml 标签 |
| `otherremarks` | 其他 | cshtml 标签 |
| `calibrationvalue` | 偏差≤10% | cshtml 标签 |
| `faultdescription` | 维修记录 / 问题描述 | cshtml 标签 |
| `maintenanceresults` | 维修结果 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_VisibilityMeter_Week_VisibilityMeter.vue）：**

bool_1 为数据传输，bool_2 为仪器表面； true = 正常（原表值 0），false = 异常（原表值 1）； remark、remark1 为两项巡查备注，remark2 为“其他”备注。 原表没有计算、自动判定、必填、格式校验或附件逻辑。


## Sup_RF_VoCsChromatotecCheck（sup_rf_common）
- 源码依据：实体 `Sup_RF_VoCsChromatotecCheck`、视图 `Sup_RF_VoCsChromatotecCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 仪器状态 - C2-C6（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_2` | 仪器状态 - C6-C12（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_3` | 炉温是否降到36℃-C2-C6（视图标签：4 / 炉温是否降到36℃） | 实体注释 |
| `bool_4` | 炉温是否降到36℃-C6-C12（视图标签：4 / 炉温是否降到36℃） | 实体注释 |
| `bool_5` | 升温过程是否平稳-C2-C6（视图标签：5 / 升温过程是否平稳） | 实体注释 |
| `bool_6` | 升温过程是否平稳-C6-C12（视图标签：5 / 升温过程是否平稳） | 实体注释 |
| `bool_7` | 炉温是否升到202℃-C2-C6（视图标签：6 / 炉温是否升到202℃） | 实体注释 |
| `bool_8` | 炉温是否升到200℃-C6-C12（视图标签：7 / 炉温是否升到200℃） | 实体注释 |
| `bool_9` | FID温度波动范围-C2-C6（视图标签：8 / FID温度波动范围 / (169.5-170.5℃)） | 实体注释 |
| `bool_10` | FID温度波动范围-C6-C12（视图标签：8 / FID温度波动范围 / (169.5-170.5℃)） | 实体注释 |
| `bool_11` | 渗透炉温度（40℃）（视图标签：1 / 渗透炉温度（40℃）） | 实体注释 |
| `bool_12` | PR1阀压力（2bar）（视图标签：2 / PR1阀压力（2bar）） | 实体注释 |
| `bool_13` | PR2阀压力（3bar）（视图标签：3 / PR2阀压力（3bar）） | 实体注释 |
| `bool_14` | 零气泵分压（4bar）（视图标签：5 / 零气泵分压（4bar）） | 实体注释 |
| `bool_15` | 零气泵排水阀（视图标签：6 / 零气泵排水阀） | 实体注释 |
| `bool_16` | 零气泵启动阀（视图标签：7 / 零气泵启动阀） | 实体注释 |
| `bool_17` | 氢气发生器输出压力（视图标签：8 / 氢气发生器输出压力 / （2000mbar）） | 实体注释 |
| `bool_18` | 是否添加纯水（视图标签：11 / 是否添加纯水） | 实体注释 |
| `string1` | 仪器状态 - 备注（视图标签：1 / 仪器状态） | 实体注释 |
| `string2` | 采样压差（hpa）- C2-C6（视图标签：2 / 采样压差（hpa）） | 实体注释 |
| `string3` | 采样压差（hpa）- C6-C12（视图标签：2 / 采样压差（hpa）） | 实体注释 |
| `string4` | 采样压差（hpa）- 备注（视图标签：2 / 采样压差（hpa）） | 实体注释 |
| `string5` | 36℃时柱压（hpa）- C2-C6（视图标签：3 / 36℃时柱压（hpa）） | 实体注释 |
| `string6` | 36℃时柱压（hpa）- C6-C12（视图标签：3 / 36℃时柱压（hpa）） | 实体注释 |
| `string7` | 36℃时柱压（hpa）- 备注（视图标签：3 / 36℃时柱压（hpa）） | 实体注释 |
| `string8` | 炉温是否降到36℃ - 备注（视图标签：4 / 炉温是否降到36℃） | 实体注释 |
| `string9` | 升温过程是否平稳 - 备注（视图标签：5 / 升温过程是否平稳） | 实体注释 |
| `string10` | 炉温是否升到202℃ - 备注（视图标签：6 / 炉温是否升到202℃） | 实体注释 |
| `string11` | 炉温是否升到200℃ - 备注（视图标签：7 / 炉温是否升到200℃） | 实体注释 |
| `string12` | FID信号值 - C2-C6（视图标签：9 / FID信号值） | 实体注释 |
| `string13` | FID信号值 - C6-C12（视图标签：9 / FID信号值） | 实体注释 |
| `string14` | FID信号值 - 备注（视图标签：9 / FID信号值） | 实体注释 |
| `string15` | 冷堆温度（℃） - C2-C6（视图标签：10 / 冷堆温度（℃）） | 实体注释 |
| `string16` | 冷堆温度（℃） - 备注（视图标签：10 / 冷堆温度（℃）） | 实体注释 |
| `string17` | 干燥管反吹流量 - C2-C6（视图标签：11 / 干燥管反吹流量） | 实体注释 |
| `string18` | 干燥管反吹流量 - 备注（视图标签：11 / 干燥管反吹流量） | 实体注释 |
| `string19` | 渗透炉温度（40℃） - 备注（视图标签：1 / 渗透炉温度（40℃）） | 实体注释 |
| `string20` | PR1阀压力（2bar） - 备注（视图标签：2 / PR1阀压力（2bar）） | 实体注释 |
| `string21` | PR2阀压力（3bar） - 备注（视图标签：3 / PR2阀压力（3bar）） | 实体注释 |
| `string22` | 零气泵压力（bar） - 内容（视图标签：4 / 零气泵压力（bar）） | 实体注释 |
| `string23` | 零气泵压力（bar） - 备注（视图标签：4 / 零气泵压力（bar）） | 实体注释 |
| `string24` | 零气泵分压（4bar） - 备注（视图标签：5 / 零气泵分压（4bar）） | 实体注释 |
| `string25` | 零气泵排水阀 - 备注（视图标签：6 / 零气泵排水阀） | 实体注释 |
| `string26` | 零气泵启动阀 - 备注（视图标签：7 / 零气泵启动阀） | 实体注释 |
| `string27` | 制氢电流值（mA） - 内容（视图标签：9 / 制氢电流值（mA）） | 实体注释 |
| `string28` | 制氢电流值（mA） - 备注（视图标签：9 / 制氢电流值（mA）） | 实体注释 |
| `string29` | 制氢电压值（V） - 内容（视图标签：10 / 制氢电压值（V）） | 实体注释 |
| `string30` | 制氢电压值（V） - 备注（视图标签：10 / 制氢电压值（V）） | 实体注释 |
| `string31` | 是否添加纯水 - 备注（视图标签：11 / 是否添加纯水） | 实体注释 |
| `string32` | MS Inlet 温度（摄氏度） - 内容（视图标签：1 / MS Inlet 温度（摄氏度）） | 实体注释 |
| `string33` | MS Inlet 温度（摄氏度） - 备注（视图标签：1 / MS Inlet 温度（摄氏度）） | 实体注释 |
| `string34` | OVEN 温度（℃） - 内容（视图标签：2 / OVEN 温度（℃）） | 实体注释 |
| `string35` | OVEN 温度（℃） - 备注（视图标签：2 / OVEN 温度（℃）） | 实体注释 |
| `string36` | Transfer line温度（℃） - 内容（视图标签：3 / Transfer line温度（℃）） | 实体注释 |
| `string37` | Transfer line温度（℃） - 备注（视图标签：3 / Transfer line温度（℃）） | 实体注释 |
| `string38` | 采样流量（ml） - 内容（视图标签：4 / 采样流量（ml）） | 实体注释 |
| `string39` | 采样流量（ml） - 备注（视图标签：4 / 采样流量（ml）） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string12`=required,double；`string13`=required,double；`string15`=required,double；`string17`=required,double；`string2`=required,double；`string3`=required,double；`string32`=required,double；`string34`=required,double；`string36`=required,double；`string38`=required,double；`string5`=required,double；`string6`=required,double


## Sup_RF_VoCsChromatotecDetectionLimitRecord（sup_rf_common）
- 源码依据：实体 `Sup_RF_VoCsChromatotecDetectionLimitRecord`、视图 `Sup_RF_VoCsChromatotecDetectionLimitRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `string1` |  | 实体注释 |
| `string2` |  | 实体注释 |
| `string3` |  | 实体注释 |
| `string4` |  | 实体注释 |
| `string5` |  | 实体注释 |
| `string6` |  | 实体注释 |
| `string7` |  | 实体注释 |
| `string8` |  | 实体注释 |
| `string9` |  | 实体注释 |
| `string10` |  | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string13` |  | 实体注释 |
| `string14` |  | 实体注释 |
| `string15` |  | 实体注释 |
| `string16` |  | 实体注释 |
| `string17` |  | 实体注释 |
| `string18` |  | 实体注释 |
| `string19` |  | 实体注释 |
| `string20` |  | 实体注释 |
| `string21` |  | 实体注释 |
| `string22` |  | 实体注释 |
| `string23` |  | 实体注释 |
| `string24` |  | 实体注释 |
| `string25` |  | 实体注释 |
| `string26` |  | 实体注释 |
| `string27` |  | 实体注释 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_VoCsDetectionLimitRecord（sup_rf_common）
- 源码依据：实体 `Sup_RF_VoCsDetectionLimitRecord`、视图 `Sup_RF_VoCsDetectionLimitRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 核查结果情况 - AMA | 实体注释 |
| `string1` |  | 实体注释 |
| `string2` |  | 实体注释 |
| `string3` |  | 实体注释 |
| `string4` |  | 实体注释 |
| `string5` |  | 实体注释 |
| `string6` |  | 实体注释 |
| `string7` |  | 实体注释 |
| `string8` |  | 实体注释 |
| `string9` |  | 实体注释 |
| `string10` |  | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string13` |  | 实体注释 |
| `string14` |  | 实体注释 |
| `string15` |  | 实体注释 |
| `string16` |  | 实体注释 |
| `string17` |  | 实体注释 |
| `string18` |  | 实体注释 |
| `string19` |  | 实体注释 |
| `string20` |  | 实体注释 |
| `string21` |  | 实体注释 |
| `string22` |  | 实体注释 |
| `string23` |  | 实体注释 |
| `string24` |  | 实体注释 |
| `string25` |  | 实体注释 |
| `string26` |  | 实体注释 |
| `string27` |  | 实体注释 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_VoCsEXPECCheck（sup_rf_common）
- 源码依据：实体 `Sup_RF_VoCsEXPECCheck`、视图 `Sup_RF_VoCsEXPECCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 仪器状态 - 低碳（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_2` | 仪器状态 - 高碳（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_3` | 零气发生器工作 - 低碳（视图标签：13 / 零气发生器工作） | 实体注释 |
| `bool_4` | 零气发生器工作 - 高碳（视图标签：13 / 零气发生器工作） | 实体注释 |
| `bool_5` | 氢气发生器工作 - 低碳（视图标签：14 / 氢气发生器工作） | 实体注释 |
| `bool_6` | 氢气发生器工作 - 高碳（视图标签：14 / 氢气发生器工作） | 实体注释 |
| `bool_7` | 氢气发生器加水（视图标签：15 / 氢气发生器加水） | 实体注释 |
| `bool_8` | 基线响应是否稳定（视图标签：16 / 基线响应是否稳定） | 实体注释 |
| `bool_9` | 采样滤膜更换（视图标签：17 / 采样滤膜更换） | 实体注释 |
| `string1` | 仪器状态（视图标签：1 / 仪器状态） | 实体注释 |
| `string2` | 柱前压（kpa） - 低碳（视图标签：2 / 柱前压（kpa）） | 实体注释 |
| `string3` | 柱前压（kpa） - 高碳（视图标签：2 / 柱前压（kpa）） | 实体注释 |
| `string4` | 柱前压（kpa） - 备注（视图标签：2 / 柱前压（kpa）） | 实体注释 |
| `string5` | 除水管温度（℃） - 低碳（视图标签：3 / 除水管温度（℃）） | 实体注释 |
| `string6` | 除水管温度（℃） - 高碳（视图标签：3 / 除水管温度（℃）） | 实体注释 |
| `string7` | 除水管温度（℃） - 备注（视图标签：3 / 除水管温度（℃）） | 实体注释 |
| `string8` | 内部温度（℃） - 低碳（视图标签：4 / 内部温度（℃）） | 实体注释 |
| `string9` | 内部温度（℃） - 高碳（视图标签：4 / 内部温度（℃）） | 实体注释 |
| `string10` | 内部温度（℃） - 备注（视图标签：4 / 内部温度（℃）） | 实体注释 |
| `string11` | L阀头温度（℃） - 低碳（视图标签：5 / L阀头温度（℃）） | 实体注释 |
| `string12` | L阀头温度（℃） - 高碳（视图标签：5 / L阀头温度（℃）） | 实体注释 |
| `string13` | L阀头温度（℃） - 备注（视图标签：5 / L阀头温度（℃）） | 实体注释 |
| `string14` | R阀头温度（℃） - 低碳（视图标签：6 / R阀头温度（℃）） | 实体注释 |
| `string15` | R阀头温度（℃） - 高碳（视图标签：6 / R阀头温度（℃）） | 实体注释 |
| `string16` | R阀头温度（℃） - 备注（视图标签：6 / R阀头温度（℃）） | 实体注释 |
| `string17` | 阀箱温度（℃） - 低碳（视图标签：7 / 阀箱温度（℃）） | 实体注释 |
| `string18` | 阀箱温度（℃） - 高碳（视图标签：7 / 阀箱温度（℃）） | 实体注释 |
| `string19` | 阀箱温度（℃） - 备注（视图标签：7 / 阀箱温度（℃）） | 实体注释 |
| `string20` | 火焰温度（℃） - 低碳（视图标签：8 / 火焰温度（℃）） | 实体注释 |
| `string21` | 火焰温度（℃） - 高碳（视图标签：8 / 火焰温度（℃）） | 实体注释 |
| `string22` | 火焰温度（℃） - 备注（视图标签：8 / 火焰温度（℃）） | 实体注释 |
| `string23` | 氢气流量(mL/min) - 低碳（视图标签：9 / 氢气流量(mL/min)） | 实体注释 |
| `string24` | 氢气流量(mL/min) - 高碳（视图标签：9 / 氢气流量(mL/min)） | 实体注释 |
| `string25` | 氢气流量(mL/min) - 备注（视图标签：9 / 氢气流量(mL/min)） | 实体注释 |
| `string26` | 空气流量(mL/min) - 低碳（视图标签：10 / 空气流量(mL/min)） | 实体注释 |
| `string27` | 空气流量(mL/min) - 高碳（视图标签：10 / 空气流量(mL/min)） | 实体注释 |
| `string28` | 空气流量(mL/min) - 备注（视图标签：10 / 空气流量(mL/min)） | 实体注释 |
| `string29` | 解吸流量(mL/min) - 低碳（视图标签：11 / 解吸流量(mL/min)） | 实体注释 |
| `string30` | 解吸流量(mL/min) - 高碳（视图标签：11 / 解吸流量(mL/min)） | 实体注释 |
| `string31` | 解吸流量(mL/min) - 备注（视图标签：11 / 解吸流量(mL/min)） | 实体注释 |
| `string32` | 氮气钢瓶气余量（Mpa） - 低碳（视图标签：12 / 氮气钢瓶气余量（Mpa）） | 实体注释 |
| `string33` | 氮气钢瓶气余量（Mpa） - 高碳（视图标签：12 / 氮气钢瓶气余量（Mpa）） | 实体注释 |
| `string34` | 氮气钢瓶气余量（Mpa） - 备注（视图标签：12 / 氮气钢瓶气余量（Mpa）） | 实体注释 |
| `string35` | 零气发生器工作（视图标签：13 / 零气发生器工作） | 实体注释 |
| `string36` | 氢气发生器工作（视图标签：14 / 氢气发生器工作） | 实体注释 |
| `string37` | 氢气发生器加水（视图标签：15 / 氢气发生器加水） | 实体注释 |
| `string38` | 基线响应是否稳定（视图标签：16 / 基线响应是否稳定） | 实体注释 |
| `string39` | 采样滤膜更换（视图标签：17 / 采样滤膜更换） | 实体注释 |
| `string40` | 仪器序列号 - 高碳（视图标签：仪器序列号 / 温度（℃）） | 实体注释 |
| `string41` | 仪器序列号 - 低碳（视图标签：仪器序列号 / 温度（℃）） | 实体注释 |
| `string42` | 温度（视图标签：湿度（%RH）） | 实体注释 |
| `string43` | 湿度 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string11`=required,double；`string12`=required,double；`string14`=required,double；`string15`=required,double；`string17`=required,double；`string18`=required,double；`string2`=required,double；`string20`=required,double；`string21`=required,double；`string23`=required,double；`string24`=required,double；`string26`=required,double；`string27`=required,double；`string29`=required,double；`string3`=required,double；`string30`=required,double；`string32`=required,double；`string33`=required,double；`string40`=required,double；`string41`=required,double；`string42`=required,double；`string5`=required,double；`string6`=required,double；`string8`=required,double；`string9`=required,double


## Sup_RF_VoCsEXPECDetectionLimitRecord（sup_rf_common）
- 源码依据：实体 `Sup_RF_VoCsEXPECDetectionLimitRecord`、视图 `Sup_RF_VoCsEXPECDetectionLimitRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 核查结果情况 | 实体注释 |
| `string1` |  | 实体注释 |
| `string2` |  | 实体注释 |
| `string3` |  | 实体注释 |
| `string4` |  | 实体注释 |
| `string5` |  | 实体注释 |
| `string6` |  | 实体注释 |
| `string7` |  | 实体注释 |
| `string8` |  | 实体注释 |
| `string9` |  | 实体注释 |
| `string10` |  | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string13` |  | 实体注释 |
| `string14` |  | 实体注释 |
| `string15` |  | 实体注释 |
| `string16` |  | 实体注释 |
| `string17` |  | 实体注释 |
| `string18` |  | 实体注释 |
| `string19` |  | 实体注释 |
| `string20` |  | 实体注释 |
| `string21` |  | 实体注释 |
| `string22` |  | 实体注释 |
| `string23` |  | 实体注释 |
| `string24` |  | 实体注释 |
| `string25` |  | 实体注释 |
| `string26` |  | 实体注释 |
| `string27` |  | 实体注释 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_VoCsTianHongCheck（sup_rf_common）
- 源码依据：实体 `Sup_RF_VoCsTianHongCheck`、视图 `Sup_RF_VoCsTianHongCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 仪器状态 - FID（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_2` | 仪器状态 - MS（视图标签：1 / 仪器状态） | 实体注释 |
| `bool_3` | 空气进样量（300ml） - FID（视图标签：2 / 空气进样量（300ml）） | 实体注释 |
| `bool_4` | 空气进样量（300ml） - MS（视图标签：2 / 空气进样量（300ml）） | 实体注释 |
| `bool_5` | 外标进样量（300ml） - FID（视图标签：3 / 外标进样量（300ml）） | 实体注释 |
| `bool_6` | 外标进样量（300ml） - MS（视图标签：3 / 外标进样量（300ml）） | 实体注释 |
| `bool_7` | 内标进样量（120ml） - MS（视图标签：4 / 内标进样量（120ml）） | 实体注释 |
| `bool_8` | TH-300软件运行情况（视图标签：5 / TH-300软件运行情况） | 实体注释 |
| `bool_9` | 捕集阱温度（小于-150℃）（视图标签：6 / 捕集阱温度 （小于-150℃）） | 实体注释 |
| `bool_10` | GC-MS软件（视图标签：8 / GC-MS软件） | 实体注释 |
| `bool_11` | 内标气（视图标签：1 / 内标气） | 实体注释 |
| `bool_12` | 外标气（视图标签：2 / 外标气） | 实体注释 |
| `bool_13` | 二氧化碳祛除管（视图标签：3 / 二氧化碳祛除管） | 实体注释 |
| `bool_14` | 颗粒物过滤膜（视图标签：4 / 颗粒物过滤膜） | 实体注释 |
| `string1` | 仪器状态-备注（视图标签：1 / 仪器状态） | 实体注释 |
| `string2` | 空气进样量（300ml）- 备注（视图标签：2 / 空气进样量（300ml）） | 实体注释 |
| `string3` | 外标进样量（300ml）- 备注（视图标签：3 / 外标进样量（300ml）） | 实体注释 |
| `string4` | 内标进样量（120ml）- 备注（视图标签：4 / 内标进样量（120ml）） | 实体注释 |
| `string5` | TH-300软件运行情况 - 备注（视图标签：5 / TH-300软件运行情况） | 实体注释 |
| `string6` | 捕集阱温度（小于-150℃）- 备注（视图标签：6 / 捕集阱温度 （小于-150℃）） | 实体注释 |
| `string7` | 除水阱温度（℃）- FID（视图标签：7 / 除水阱温度（℃）） | 实体注释 |
| `string8` | 除水阱温度（℃）- MS（视图标签：7 / 除水阱温度（℃）） | 实体注释 |
| `string9` | 除水阱温度（℃） - 备注（视图标签：7 / 除水阱温度（℃）） | 实体注释 |
| `string10` | GC-MS软件 - 备注（视图标签：8 / GC-MS软件） | 实体注释 |
| `string11` | 氦气（Mpa） - 内容（视图标签：1 / 氦气（Mpa）） | 实体注释 |
| `string12` | 氦气（Mpa） - 备注（视图标签：1 / 氦气（Mpa）） | 实体注释 |
| `string13` | 氮气（Mpa） - 内容（视图标签：2 / 氮气（Mpa）） | 实体注释 |
| `string14` | 氮气（Mpa） - 备注（视图标签：2 / 氮气（Mpa）） | 实体注释 |
| `string15` | 氢气（MPa） - 内容（视图标签：3 / 氢气（MPa）） | 实体注释 |
| `string16` | 氢气（MPa） - 备注（视图标签：3 / 氢气（MPa）） | 实体注释 |
| `string17` | 零气系统 - 内容（视图标签：4 / 零气系统） | 实体注释 |
| `string18` | 零气系统 - 备注（视图标签：4 / 零气系统） | 实体注释 |
| `string19` | 内标气 - 备注（视图标签：1 / 内标气） | 实体注释 |
| `string20` | 外标气 - 备注（视图标签：2 / 外标气） | 实体注释 |
| `string21` | 二氧化碳祛除管 - 备注（视图标签：3 / 二氧化碳祛除管） | 实体注释 |
| `string22` | 颗粒物过滤膜 - 备注（视图标签：4 / 颗粒物过滤膜） | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string11`=required,double；`string13`=required,double；`string15`=required,double；`string17`=required,double；`string7`=required,double；`string8`=required,double


## Sup_RF_VoCsWHTHDetectionLimitRecord（sup_rf_common）
- 源码依据：实体 `Sup_RF_VoCsWHTHDetectionLimitRecord`、视图 `Sup_RF_VoCsWHTHDetectionLimitRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 核查结果情况 - | 实体注释 |
| `string1` |  | 实体注释 |
| `string2` |  | 实体注释 |
| `string3` |  | 实体注释 |
| `string4` |  | 实体注释 |
| `string5` |  | 实体注释 |
| `string6` |  | 实体注释 |
| `string7` |  | 实体注释 |
| `string8` |  | 实体注释 |
| `string9` |  | 实体注释 |
| `string10` |  | 实体注释 |
| `string11` |  | 实体注释 |
| `string12` |  | 实体注释 |
| `string13` |  | 实体注释 |
| `string14` |  | 实体注释 |
| `string15` |  | 实体注释 |
| `string16` |  | 实体注释 |
| `string17` |  | 实体注释 |
| `string18` |  | 实体注释 |
| `string19` |  | 实体注释 |
| `string20` |  | 实体注释 |
| `string21` |  | 实体注释 |
| `string22` |  | 实体注释 |
| `string23` |  | 实体注释 |
| `string24` |  | 实体注释 |
| `string25` |  | 实体注释 |
| `string26` |  | 实体注释 |
| `string27` |  | 实体注释 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_VocsFlowCheck（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VocsFlowCheck`、视图 `Sup_RF_VocsFlowCheck.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：流量计有效期： / 测试开始时间： / 测试结束时间：） | 实体注释 |
| `time2` | 结束时间（视图标签：流量计有效期： / 测试开始时间： / 测试结束时间：） | 实体注释 |
| `time3` | 流量计有效期： / 测试开始时间： / 测试结束时间： | cshtml 标签 |
| `bool_1` | （视图绑定，含义见标签） | cshtml 标签 |
| `bool_2` | 是 否 | cshtml 标签 |
| `string1` | 室内温湿度及气压： / 流量计编号： / 质控检查频率： / 每月一次 | cshtml 标签 |
| `string2` | 室内温湿度及气压： / 流量计编号： / 质控检查频率： / 每月一次 | cshtml 标签 |
| `string4` | （视图绑定，含义见标签） | cshtml 标签 |
| `string5` | （视图绑定，含义见标签） | cshtml 标签 |
| `string6` | （视图绑定，含义见标签） | cshtml 标签 |
| `string7` | （视图绑定，含义见标签） | cshtml 标签 |
| `string9` | 是 否 / 是 否 | cshtml 标签 |


## Sup_RF_VocsSceneCheck（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VocsSceneCheck`、视图 `Sup_RF_VocsSceneCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 3 / 大气采样系统 | cshtml 标签 |
| `bool_2` | 1 / 仪器状态 | cshtml 标签 |
| `bool_3` | 1 / 仪器状态 | cshtml 标签 |
| `bool_4` | 2 / 空气进样量（300ml) | cshtml 标签 |
| `bool_5` | 2 / 空气进样量（300ml) | cshtml 标签 |
| `bool_6` | 3 / 外标进样量（ | cshtml 标签 |
| `bool_7` | 3 / 外标进样量（ | cshtml 标签 |
| `bool_8` | 4 / 内标进样量（300ml) | cshtml 标签 |
| `bool_9` | 5 / ACGC软件运行情况 | cshtml 标签 |
| `bool_10` | 5 / ACGC软件运行情况 | cshtml 标签 |
| `bool_11` | 6 / 冷阱温度（小于 | cshtml 标签 |
| `bool_12` | 6 / 冷阱温度（小于 | cshtml 标签 |
| `bool_13` | 7 / GCMS软件 | cshtml 标签 |
| `bool_14` | 1 / 氮气（MPa) | cshtml 标签 |
| `bool_15` | 1 / 氦气（MPa) | cshtml 标签 |
| `bool_16` | 1 / 氢气压力（0.4MPa） | cshtml 标签 |
| `bool_17` | 2 / 空气压力（0.4MPa） | cshtml 标签 |
| `bool_18` | 3 / 硅胶 | cshtml 标签 |
| `bool_19` | 4 / 活性炭 | cshtml 标签 |
| `bool_20` | 1 / 内标气 | cshtml 标签 |
| `bool_21` | 2 / 外标气 | cshtml 标签 |
| `bool_22` | 3 / 二氧化碳捕集管 | cshtml 标签 |
| `bool_23` | 4 / 颗粒物过滤膜 | cshtml 标签 |
| `bool_24` | 5 / 硅胶 | cshtml 标签 |
| `bool_25` | 6 / 纯水 | cshtml 标签 |
| `remark1` | 1 / 温度（＜25℃） | cshtml 标签 |
| `remark2` | 2 / 湿度（＜80%） | cshtml 标签 |
| `remark3` | 3 / 大气采样系统 | cshtml 标签 |
| `remark4` | 1 / 仪器状态 | cshtml 标签 |
| `remark5` | 2 / 空气进样量（300ml) | cshtml 标签 |
| `remark6` | 3 / 外标进样量（ | cshtml 标签 |
| `remark7` | 4 / 内标进样量（300ml) | cshtml 标签 |
| `remark8` | 5 / ACGC软件运行情况 | cshtml 标签 |
| `remark9` | 6 / 冷阱温度（小于 | cshtml 标签 |
| `string1` | 1 / 温度（＜25℃） | cshtml 标签 |
| `string2` | 2 / 湿度（＜80%） | cshtml 标签 |
| `remark10` | 7 / GCMS软件 | cshtml 标签 |
| `remark11` | 1 / 氮气（MPa) | cshtml 标签 |
| `remark12` | 1 / 氦气（MPa) | cshtml 标签 |
| `remark13` | 1 / 氢气压力（0.4MPa） | cshtml 标签 |
| `remark14` | 2 / 空气压力（0.4MPa） | cshtml 标签 |
| `remark15` | 3 / 硅胶 | cshtml 标签 |
| `remark16` | 4 / 活性炭 | cshtml 标签 |
| `remark17` | 1 / 内标气 | cshtml 标签 |
| `remark18` | 2 / 外标气 | cshtml 标签 |
| `remark19` | 3 / 二氧化碳捕集管 | cshtml 标签 |
| `remark20` | 4 / 颗粒物过滤膜 | cshtml 标签 |
| `remark21` | 5 / 硅胶 | cshtml 标签 |
| `remark22` | 6 / 纯水 | cshtml 标签 |


## Sup_RF_VocsSinglePoint（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VocsSinglePoint`、视图 `Sup_RF_VocsSinglePoint.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `diff` | 偏差（%） / 备注 | cshtml 标签 |
| `time1` | 开始时间（视图标签：标准化合物数量： / 数据日期：） | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `dremark` | 偏差（%） / 备注 | cshtml 标签 |
| `string1` | 标准化合物数量： / 数据日期： | cshtml 标签 |
| `response` | 偏差（%） / 备注 | cshtml 标签 |
| `detailstr` | 偏差（%） / 备注 | cshtml 标签 |


## Sup_RF_VocsStandardCurveCalibrate（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/VOCs在线监测仪.docx
- 源码依据：实体 `Sup_RF_VocsStandardCurveCalibrate`、视图 `Sup_RF_VocsStandardCurveCalibrate.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `r` | 10ppb | cshtml 标签 |
| `time1` | 开始时间（视图标签：标准化合物数量：） | 实体注释 |
| `time2` | 结束时间（视图标签：标准化合物数量： / 校准开始时间：） | 实体注释 |
| `string1` | （视图绑定，含义见标签） | cshtml 标签 |
| `detailstr` | （视图绑定，含义见标签） | cshtml 标签 |
| `response2` | 8ppb / 10ppb | cshtml 标签 |
| `response4` | 8ppb / 10ppb | cshtml 标签 |
| `response6` | 8ppb / 10ppb | cshtml 标签 |
| `response8` | 8ppb / 10ppb | cshtml 标签 |
| `response05` | 8ppb / 10ppb | cshtml 标签 |
| `response10` | 8ppb / 10ppb | cshtml 标签 |


## Sup_RF_WaterSolubleIonsQuality（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/水溶性离子.docx
- 源码依据：实体 `Sup_RF_WaterSolubleIonsQuality`、视图 `Sup_RF_WaterSolubleIonsQuality.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |

**Vue 头部字段映射（Sup_QC_RF_WaterSolubleIonsQuality_WaterSolubleIons.vue）：**

remark 为备注，commonFile 为附件。


## Sup_RF_WeekSecurityCheck（sup_rf_common）
- 源码依据：实体 `Sup_RF_WeekSecurityCheck`、视图 `Sup_RF_WeekSecurityCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：6 / 防雷检定是否有效期内（每年检定，有效期1年）） | 实体注释 |
| `time2` | 结束时间（视图标签：3 / 自动灭火器上次更换日期） | 实体注释 |
| `time3` | 6 / 手持式灭火器上次更换日期 | cshtml 标签 |
| `bool_1` | 1 / 站房外部环境卫生（是否有垃圾、杂物未及时清理） | cshtml 标签 |
| `bool_2` | 2 / 站房采样平台排水系统是否堵塞、排水顺畅 | cshtml 标签 |
| `bool_3` | 3 / 检查采样法兰、线路密封胶是否开裂（如开裂需及时重新密封） | cshtml 标签 |
| `bool_4` | 4 / 站房采样平台楼梯是否正常关闭 | cshtml 标签 |
| `bool_5` | 5 / 站房采样平台是否有设备、采样头等未进行固定，乱摆放现象 | cshtml 标签 |
| `bool_6` | 6 / 站房所在建筑楼面是否有积水情况 | cshtml 标签 |
| `bool_7` | 7 / 站房门锁是否正常，门禁系统是否工作正常 | cshtml 标签 |
| `bool_8` | 8 / 站房内部环境卫生（桌面干净整齐无杂物、清洁用具统一摆放、垃圾杂物及时清理） | cshtml 标签 |
| `bool_9` | 9 / 站房内部平面是否有塌陷、破损 | cshtml 标签 |
| `bool_10` | 10 / 站房空调是否正常运行（是否有报警、制冷效果、自动切换系统、是否正常） | cshtml 标签 |
| `bool_11` | 11 / 站房除湿机是否正常运行（水满报警、排水不畅等） | cshtml 标签 |
| `bool_14` | 14 / 站房内部是否有设备、临时用电等未进行固定，乱摆放现象 | cshtml 标签 |
| `bool_15` | 15 / 检查站房内部是否有漏水情况（采样法兰等开孔处有无渗水） | cshtml 标签 |
| `bool_16` | 16 / 排风扇是否工作正常 | cshtml 标签 |
| `bool_17` | 17 / 站房内部照明是否正常 | cshtml 标签 |
| `bool_18` | 18 / 检查各仪器设备表面灰尘 | cshtml 标签 |
| `bool_19` | 19 / 站房内部工具、耗材等是否按要求规整摆放 | cshtml 标签 |
| `bool_21` | 2 / UPS是否工作正常（如有） | cshtml 标签 |
| `bool_22` | 3 / 仪器供电插座或者排插是否存在超功率使用安全隐患 | cshtml 标签 |
| `bool_23` | 4 / 仪器线路、管路是否整理有序 | cshtml 标签 |
| `bool_24` | 5 / 空气开关、断路器、蓄电池等是否有发热情况 | cshtml 标签 |
| `bool_26` | 7 / 站房外部用电线路是否有裸露、破损等现象 | cshtml 标签 |
| `bool_27` | 8 / 站房内部用电线路是否有裸露、破损等现象 | cshtml 标签 |
| `bool_28` | 1 / 自动灭火器是否在有效期内 | cshtml 标签 |
| `bool_29` | 2 / 自动灭火器充体压力是否在要求范围内 | cshtml 标签 |
| `bool_31` | 4 / 手持式灭火器是否在有效期内 | cshtml 标签 |
| `bool_32` | 5 / 手持式灭火器充体压力是否在要求范围内 | cshtml 标签 |
| `bool_34` | 7 / 是否发现易燃易爆危险品未按要求存放、撤走（如无水乙醇等） | cshtml 标签 |
| `bool_35` | 1 / 视频监控设备是否正常运行（如有） | cshtml 标签 |
| `bool_36` | 2 / 站房环境监控设备是否正常运行，烟雾传感器、气体泄露传感器等（如有） | cshtml 标签 |
| `bool_37` | 3 / 气瓶是否有安全固定措施（8L以上） | cshtml 标签 |
| `remark1` | 1 / 站房外部环境卫生（是否有垃圾、杂物未及时清理） | cshtml 标签 |
| `remark2` | 2 / 站房采样平台排水系统是否堵塞、排水顺畅 | cshtml 标签 |
| `remark3` | 3 / 检查采样法兰、线路密封胶是否开裂（如开裂需及时重新密封） | cshtml 标签 |
| `remark4` | 4 / 站房采样平台楼梯是否正常关闭 | cshtml 标签 |
| `remark5` | 5 / 站房采样平台是否有设备、采样头等未进行固定，乱摆放现象 | cshtml 标签 |
| `remark6` | 6 / 站房所在建筑楼面是否有积水情况 | cshtml 标签 |
| `remark7` | 7 / 站房门锁是否正常，门禁系统是否工作正常 | cshtml 标签 |
| `remark8` | 8 / 站房内部环境卫生（桌面干净整齐无杂物、清洁用具统一摆放、垃圾杂物及时清理） | cshtml 标签 |
| `remark9` | 9 / 站房内部平面是否有塌陷、破损 | cshtml 标签 |
| `remark10` | 10 / 站房空调是否正常运行（是否有报警、制冷效果、自动切换系统、是否正常） | cshtml 标签 |
| `remark11` | 11 / 站房除湿机是否正常运行（水满报警、排水不畅等） | cshtml 标签 |
| `remark12` | 12 / 站房内部温度是否满足要求（25±5℃） | cshtml 标签 |
| `remark13` | 13 / 站房内部湿度是否满足要求（≤80%） | cshtml 标签 |
| `remark14` | 14 / 站房内部是否有设备、临时用电等未进行固定，乱摆放现象 | cshtml 标签 |
| `remark15` | 15 / 检查站房内部是否有漏水情况（采样法兰等开孔处有无渗水） | cshtml 标签 |
| `remark16` | 16 / 排风扇是否工作正常 | cshtml 标签 |
| `remark17` | 17 / 站房内部照明是否正常 | cshtml 标签 |
| `remark18` | 18 / 检查各仪器设备表面灰尘 | cshtml 标签 |
| `remark19` | 19 / 站房内部工具、耗材等是否按要求规整摆放 | cshtml 标签 |
| `remark20` | 1 / 稳压器是否工作正常 | cshtml 标签 |
| `remark21` | 2 / UPS是否工作正常（如有） | cshtml 标签 |
| `remark22` | 3 / 仪器供电插座或者排插是否存在超功率使用安全隐患 | cshtml 标签 |
| `remark23` | 4 / 仪器线路、管路是否整理有序 | cshtml 标签 |
| `remark24` | 5 / 空气开关、断路器、蓄电池等是否有发热情况 | cshtml 标签 |
| `remark25` | 6 / 防雷检定是否有效期内（每年检定，有效期1年） | cshtml 标签 |
| `remark26` | 7 / 站房外部用电线路是否有裸露、破损等现象 | cshtml 标签 |
| `remark27` | 8 / 站房内部用电线路是否有裸露、破损等现象 | cshtml 标签 |
| `remark28` | 1 / 自动灭火器是否在有效期内 | cshtml 标签 |
| `remark29` | 2 / 自动灭火器充体压力是否在要求范围内 | cshtml 标签 |
| `remark30` | 3 / 自动灭火器上次更换日期 | cshtml 标签 |
| `remark31` | 4 / 手持式灭火器是否在有效期内 | cshtml 标签 |
| `remark32` | 5 / 手持式灭火器充体压力是否在要求范围内 | cshtml 标签 |
| `remark33` | 6 / 手持式灭火器上次更换日期 | cshtml 标签 |
| `remark34` | 7 / 是否发现易燃易爆危险品未按要求存放、撤走（如无水乙醇等） | cshtml 标签 |
| `remark35` | 1 / 视频监控设备是否正常运行（如有） | cshtml 标签 |
| `remark36` | 2 / 站房环境监控设备是否正常运行，烟雾传感器、气体泄露传感器等（如有） | cshtml 标签 |
| `remark37` | 3 / 气瓶是否有安全固定措施（8L以上） | cshtml 标签 |
| `string12` | 12 / 站房内部温度是否满足要求（25±5℃） | cshtml 标签 |
| `string13` | 13 / 站房内部湿度是否满足要求（≤80%） | cshtml 标签 |
| `string20` | 1 / 稳压器是否工作正常 | cshtml 标签 |


## Sup_RF_Week_BJCCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/BC.docx
- 源码依据：实体 `Sup_RF_Week_BJCCheck`、视图 `Sup_RF_Week_BJCCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 边界层大气成分二维高光谱扫描与分析仪 / 数据采集是否正常 | cshtml 标签 |
| `bool_2` | 镜头是否干净 | cshtml 标签 |
| `bool_3` | 供电是否正常 | cshtml 标签 |
| `remark1` | 边界层大气成分二维高光谱扫描与分析仪 / 数据采集是否正常 | cshtml 标签 |
| `remark2` | 镜头是否干净 | cshtml 标签 |
| `remark3` | 供电是否正常 | cshtml 标签 |
| `remark4` | 备注： | cshtml 标签 |


## Sup_RF_Week_FKXLiDAR（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/风廓线雷达.docx
- 源码依据：实体 `Sup_RF_Week_FKXLiDAR`、视图 `Sup_RF_Week_FKXLiDAR.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 供电储能检查 / 市电供电，UPS供电正常，太阳能等自供电系统 | cshtml 标签 |
| `bool_2` | 设备内部环境检查 / 温度： / ℃ | cshtml 标签 |
| `bool_3` | 异响噪音检查 / 无异响及噪音 | cshtml 标签 |
| `bool_4` | 网络相关项目检查 / 网络连接正常，网速正常 | cshtml 标签 |
| `bool_5` | 机壳漏水和腐蚀检查 / 机壳没有漏水痕迹，表面没有明显腐蚀以及掉漆 | cshtml 标签 |
| `bool_6` | 保护窗检查 / 保护窗表面清洁没有污渍和损坏 | cshtml 标签 |
| `bool_7` | 散热窗口检查 / 散热风扇工作正常，防尘滤网没有堵塞 | cshtml 标签 |
| `bool_8` | 激光安全防护检查 / 激光防护警示牌无破损无脏污 | cshtml 标签 |
| `bool_9` | 运行自检检查 / 开机正常运行无报警报错 | cshtml 标签 |
| `bool_10` | 软件运行检查 / 采集软件及数据查看软件运行正常无卡死及错误 | cshtml 标签 |
| `bool_11` | 软硬件通讯检查 / 软硬件数据通讯正常、数据正常采集 | cshtml 标签 |
| `bool_12` | 参数设置检查 / 各参数设置在规定域值范围内 | cshtml 标签 |
| `bool_13` | 激光器外壳温度 / 0℃＜外壳温度＜45℃ | cshtml 标签 |
| `bool_14` | 放大器外壳温度 / 0℃＜外壳温度＜45℃ | cshtml 标签 |
| `bool_15` | 放大器泵浦电流 / 泵浦电流≥2200mA | cshtml 标签 |
| `bool_16` | 放大器输出功率 / 输出功率≥800mW | cshtml 标签 |
| `bool_17` | 伺服工作状态检查 / 伺服执行正常，没有报警 | cshtml 标签 |
| `bool_18` | 实时数据更新检查 / 数据更新采集率≧98%，实时数据刷新正常 | cshtml 标签 |
| `bool_19` | 数据自动存储检查 / 数据存储完整 | cshtml 标签 |
| `bool_20` | 历史数据查看检查 / 历史数据查看正常 | cshtml 标签 |
| `bool_21` | 有效探测距离检查 / 实时数据的有效探测距离正常 | cshtml 标签 |
| `remark1` | 备注描述 | cshtml 标签 |
| `remark2` | 备注描述 | cshtml 标签 |
| `remark3` | 备注描述 | cshtml 标签 |
| `remark4` | 备注描述 | cshtml 标签 |
| `string1` | 设备内部环境检查 / 温度： / ℃ | cshtml 标签 |
| `string2` | 湿度： / % | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_Week_FKXLiDAR_WindProfileRadar.vue）：**

bool_1 至 bool_21 为检查结果；string1、string2 为设备内部温度、湿度； remark、remark1、remark2、remark3 为四个检查区段的备注；commonFile 为附件。


## Sup_RF_Week_HONOCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/HONO.docx
- 源码依据：实体 `Sup_RF_Week_HONOCheck`、视图 `Sup_RF_Week_HONOCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：维护单位 / 安装地点 / 维护时间） | 实体注释 |
| `time2` | 结束时间（视图标签：零点校正 / ＜24小时） | 实体注释 |
| `bool_6` | 1 / 仪器检查 / 分析仪主机 / 运行观测中 / 正常 | cshtml 标签 |
| `bool_7` | 循环水浴 / 25℃/>2/3 | cshtml 标签 |
| `bool_8` | 取气盒 / 固定稳固度；三通接头、内部连接 (in、out、w液路接头、气路接头) / 正常 | cshtml 标签 |
| `bool_9` | 零气钢瓶 / ＞0.5bar | cshtml 标签 |
| `bool_10` | 零点校正 / ＜24小时 | cshtml 标签 |
| `bool_11` | 设备校正 / ＞0.995 | cshtml 标签 |
| `bool_12` | 数据状态 / 仪器显示、工控机数采 / 正常 | cshtml 标签 |
| `bool_13` | 2 / 系统检查 / 显示屏 / 运行状态、设备控制是否正常 / 正常 | cshtml 标签 |
| `bool_14` | 蠕动泵 / 基本状态 / 泵管堵塞、接头松动 / 正常 | cshtml 标签 |
| `bool_15` | 转速是否匹配 / 正常 | cshtml 标签 |
| `bool_16` | 泵管是否需要更换 / 更换时间 | cshtml 标签 |
| `bool_17` | 泵管卡子松紧度 / 上调1档 | cshtml 标签 |
| `bool_18` | 12个通道状态确认 / R1-1in / 无气泡 | cshtml 标签 |
| `bool_19` | R1-2in / 无气泡 | cshtml 标签 |
| `bool_20` | R2-1 / 无气泡 | cshtml 标签 |
| `bool_21` | R2-2 / 无气泡 | cshtml 标签 |
| `bool_22` | R1-1out / 无气泡 | cshtml 标签 |
| `bool_23` | R1-2out / 无气泡 | cshtml 标签 |
| `bool_24` | ABS-1 / 无气泡 | cshtml 标签 |
| `bool_25` | ABS-2 / 无气泡 | cshtml 标签 |
| `bool_26` | W1 / 间隔气泡 | cshtml 标签 |
| `bool_27` | W2 / 间隔气泡 | cshtml 标签 |
| `bool_28` | 中和液 in / 无气泡 | cshtml 标签 |
| `bool_29` | 中和液 out / 间隔气泡 | cshtml 标签 |
| `bool_30` | 排废 / 废液排 / 连接正常 / 无异常 | cshtml 标签 |
| `bool_31` | 废液管 / 废液出口 / 间隔气泡 | cshtml 标签 |
| `bool_32` | 光信号 / 谱仪信息 / ch1积分时间 / ＜80 | cshtml 标签 |
| `bool_33` | ch2积分时间 / ＜80 | cshtml 标签 |
| `bool_34` | 光谱1-550nm强度 / ＞3,500 | cshtml 标签 |
| `bool_35` | 光谱2-550nm强度 / ＞3,500 | cshtml 标签 |
| `bool_36` | 吸光度 / 吸光度1 / ＜2 | cshtml 标签 |
| `bool_37` | 吸光度2 / ＜2 | cshtml 标签 |
| `bool_38` | 其他组件 / 内部液路管 / 紧固度、有无漏液 / 正常 | cshtml 标签 |
| `bool_39` | 空气泵 / 正常运转、无异响 / 正常 | cshtml 标签 |
| `bool_40` | 安全瓶 / 无进液 / 无进液 | cshtml 标签 |
| `bool_41` | 光纤 / 无折损、接头无松动 / 无松动 | cshtml 标签 |
| `bool_42` | 空气过滤膜 / 检查是否需要更换 / 正常 | cshtml 标签 |
| `bool_43` | 光源LED / 正常光照 / 正常 | cshtml 标签 |
| `bool_44` | 3 / 试剂废液 / 试剂袋 / 是否泄漏 / 无泄漏 | cshtml 标签 |
| `bool_45` | R2避光保护 / 避光保护 | cshtml 标签 |
| `bool_46` | 剩余量是否充足 / ＞2/5 | cshtml 标签 |
| `bool_47` | 废液桶 / 废液排出、废液桶是否更换 / ＜2/3 | cshtml 标签 |
| `remark6` | 1 / 仪器检查 / 分析仪主机 / 运行观测中 / 正常 | cshtml 标签 |
| `remark7` | 循环水浴 / 25℃/>2/3 | cshtml 标签 |
| `remark8` | 取气盒 / 固定稳固度；三通接头、内部连接 (in、out、w液路接头、气路接头) / 正常 | cshtml 标签 |
| `remark9` | 零气钢瓶 / ＞0.5bar | cshtml 标签 |
| `string1` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string2` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string3` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string4` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string5` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string6` | 1 / 仪器检查 / 分析仪主机 / 运行观测中 / 正常 | cshtml 标签 |
| `string7` | 循环水浴 / 25℃/>2/3 | cshtml 标签 |
| `string8` | 取气盒 / 固定稳固度；三通接头、内部连接 (in、out、w液路接头、气路接头) / 正常 | cshtml 标签 |
| `string9` | 零气钢瓶 / ＞0.5bar | cshtml 标签 |
| `remark10` | 零点校正 / ＜24小时 | cshtml 标签 |
| `remark11` | 设备校正 / ＞0.995 | cshtml 标签 |
| `remark12` | 数据状态 / 仪器显示、工控机数采 / 正常 | cshtml 标签 |
| `remark13` | 2 / 系统检查 / 显示屏 / 运行状态、设备控制是否正常 / 正常 | cshtml 标签 |
| `remark14` | 蠕动泵 / 基本状态 / 泵管堵塞、接头松动 / 正常 | cshtml 标签 |
| `remark15` | 转速是否匹配 / 正常 | cshtml 标签 |
| `remark16` | 泵管是否需要更换 / 更换时间 | cshtml 标签 |
| `remark17` | 泵管卡子松紧度 / 上调1档 | cshtml 标签 |
| `remark18` | 12个通道状态确认 / R1-1in / 无气泡 | cshtml 标签 |
| `remark19` | R1-2in / 无气泡 | cshtml 标签 |
| `remark20` | R2-1 / 无气泡 | cshtml 标签 |
| `remark21` | R2-2 / 无气泡 | cshtml 标签 |
| `remark22` | R1-1out / 无气泡 | cshtml 标签 |
| `remark23` | R1-2out / 无气泡 | cshtml 标签 |
| `remark24` | ABS-1 / 无气泡 | cshtml 标签 |
| `remark25` | ABS-2 / 无气泡 | cshtml 标签 |
| `remark26` | W1 / 间隔气泡 | cshtml 标签 |
| `remark27` | W2 / 间隔气泡 | cshtml 标签 |
| `remark28` | 中和液 in / 无气泡 | cshtml 标签 |
| `remark29` | 中和液 out / 间隔气泡 | cshtml 标签 |
| `remark30` | 排废 / 废液排 / 连接正常 / 无异常 | cshtml 标签 |
| `remark31` | 废液管 / 废液出口 / 间隔气泡 | cshtml 标签 |
| `remark32` | 光信号 / 谱仪信息 / ch1积分时间 / ＜80 | cshtml 标签 |
| `remark33` | ch2积分时间 / ＜80 | cshtml 标签 |
| `remark34` | 光谱1-550nm强度 / ＞3,500 | cshtml 标签 |
| `remark35` | 光谱2-550nm强度 / ＞3,500 | cshtml 标签 |
| `remark36` | 吸光度 / 吸光度1 / ＜2 | cshtml 标签 |
| `remark37` | 吸光度2 / ＜2 | cshtml 标签 |
| `remark38` | 其他组件 / 内部液路管 / 紧固度、有无漏液 / 正常 | cshtml 标签 |
| `remark39` | 空气泵 / 正常运转、无异响 / 正常 | cshtml 标签 |
| `remark40` | 安全瓶 / 无进液 / 无进液 | cshtml 标签 |
| `remark41` | 光纤 / 无折损、接头无松动 / 无松动 | cshtml 标签 |
| `remark42` | 空气过滤膜 / 检查是否需要更换 / 正常 | cshtml 标签 |
| `remark43` | 光源LED / 正常光照 / 正常 | cshtml 标签 |
| `remark44` | 3 / 试剂废液 / 试剂袋 / 是否泄漏 / 无泄漏 | cshtml 标签 |
| `remark45` | R2避光保护 / 避光保护 | cshtml 标签 |
| `remark46` | 剩余量是否充足 / ＞2/5 | cshtml 标签 |
| `remark47` | 废液桶 / 废液排出、废液桶是否更换 / ＜2/3 | cshtml 标签 |
| `remark49` | 异常问题处理记录： | cshtml 标签 |
| `remark50` | 备注： | cshtml 标签 |
| `string10` | 零点校正 / ＜24小时 | cshtml 标签 |
| `string11` | 设备校正 / ＞0.995 | cshtml 标签 |
| `string12` | 数据状态 / 仪器显示、工控机数采 / 正常 | cshtml 标签 |
| `string13` | 2 / 系统检查 / 显示屏 / 运行状态、设备控制是否正常 / 正常 | cshtml 标签 |
| `string14` | 蠕动泵 / 基本状态 / 泵管堵塞、接头松动 / 正常 | cshtml 标签 |
| `string15` | 转速是否匹配 / 正常 | cshtml 标签 |
| `string16` | 泵管是否需要更换 / 更换时间 | cshtml 标签 |
| `string17` | 泵管卡子松紧度 / 上调1档 | cshtml 标签 |
| `string18` | 12个通道状态确认 / R1-1in / 无气泡 | cshtml 标签 |
| `string19` | R1-2in / 无气泡 | cshtml 标签 |
| `string20` | R2-1 / 无气泡 | cshtml 标签 |
| `string21` | R2-2 / 无气泡 | cshtml 标签 |
| `string22` | R1-1out / 无气泡 | cshtml 标签 |
| `string23` | R1-2out / 无气泡 | cshtml 标签 |
| `string24` | ABS-1 / 无气泡 | cshtml 标签 |
| `string25` | ABS-2 / 无气泡 | cshtml 标签 |
| `string26` | W1 / 间隔气泡 | cshtml 标签 |
| `string27` | W2 / 间隔气泡 | cshtml 标签 |
| `string28` | 中和液 in / 无气泡 | cshtml 标签 |
| `string29` | 中和液 out / 间隔气泡 | cshtml 标签 |
| `string30` | 排废 / 废液排 / 连接正常 / 无异常 | cshtml 标签 |
| `string31` | 废液管 / 废液出口 / 间隔气泡 | cshtml 标签 |
| `string32` | 光信号 / 谱仪信息 / ch1积分时间 / ＜80 | cshtml 标签 |
| `string33` | ch2积分时间 / ＜80 | cshtml 标签 |
| `string34` | 光谱1-550nm强度 / ＞3,500 | cshtml 标签 |
| `string35` | 光谱2-550nm强度 / ＞3,500 | cshtml 标签 |
| `string36` | 吸光度 / 吸光度1 / ＜2 | cshtml 标签 |
| `string37` | 吸光度2 / ＜2 | cshtml 标签 |
| `string38` | 其他组件 / 内部液路管 / 紧固度、有无漏液 / 正常 | cshtml 标签 |
| `string39` | 空气泵 / 正常运转、无异响 / 正常 | cshtml 标签 |
| `string40` | 安全瓶 / 无进液 / 无进液 | cshtml 标签 |
| `string41` | 光纤 / 无折损、接头无松动 / 无松动 | cshtml 标签 |
| `string42` | 空气过滤膜 / 检查是否需要更换 / 正常 | cshtml 标签 |
| `string43` | 光源LED / 正常光照 / 正常 | cshtml 标签 |
| `string44` | 3 / 试剂废液 / 试剂袋 / 是否泄漏 / 无泄漏 | cshtml 标签 |
| `string45` | R2避光保护 / 避光保护 | cshtml 标签 |
| `string46` | 剩余量是否充足 / ＞2/5 | cshtml 标签 |
| `string47` | 废液桶 / 废液排出、废液桶是否更换 / ＜2/3 | cshtml 标签 |
| `string50` | 循环水浴 / 25℃/>2/3 | cshtml 标签 |
| `string51` | 零气钢瓶 / ＞0.5bar | cshtml 标签 |
| `string52` | 设备校正 / ＞0.995 | cshtml 标签 |

**平台校验器：**`string1`=required；`string2`=required；`string3`=required；`string4`=required；`string5`=required


## Sup_RF_Week_HONOQC（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/HONO.docx
- 源码依据：实体 `Sup_RF_Week_HONOQC`、视图 `Sup_RF_Week_HONOQC.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：维护单位 / 安装地点 / 维护时间） | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `string1` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string2` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string3` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string4` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string5` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string6` | 序号 / 标准溶液mg/L / HONO浓度ppb / 归零吸光度 / 气体流速mL/min / 液体流速mL/min | cshtml 标签 |
| `string7` | 序号 / 标准溶液mg/L / HONO浓度ppb / 归零吸光度 / 气体流速mL/min / 液体流速mL/min | cshtml 标签 |
| `remark50` | 备注： | cshtml 标签 |
| `string11` | 1 / 0 / 通道 | cshtml 标签 |
| `string12` | 1 / 0 / 通道 | cshtml 标签 |
| `string13` | 1 / 0 / 通道 | cshtml 标签 |
| `string14` | 1 / 0 / 通道 | cshtml 标签 |
| `string15` | 1 / 0 / 通道 | cshtml 标签 |
| `string16` | 1 / 0 / 通道 | cshtml 标签 |
| `string17` | 1 / 0 / 通道 | cshtml 标签 |
| `string18` | 1 / 0 / 通道 | cshtml 标签 |
| `string19` | 1 / 0 / 通道 | cshtml 标签 |
| `string21` | 2 / 0.0050 / ch1-550 | cshtml 标签 |
| `string22` | 2 / 0.0050 / ch1-550 | cshtml 标签 |
| `string23` | 2 / 0.0050 / ch1-550 | cshtml 标签 |
| `string24` | 2 / 0.0050 / ch1-550 | cshtml 标签 |
| `string25` | 2 / 0.0050 / ch1-550 | cshtml 标签 |
| `string26` | 2 / 0.0050 / ch1-550 | cshtml 标签 |
| `string27` | 2 / 0.0050 / ch1-550 | cshtml 标签 |
| `string28` | 2 / 0.0050 / ch1-550 | cshtml 标签 |
| `string29` | 2 / 0.0050 / ch1-550 | cshtml 标签 |
| `string31` | 3 / 0.0100 / ch1-600 | cshtml 标签 |
| `string32` | 3 / 0.0100 / ch1-600 | cshtml 标签 |
| `string33` | 3 / 0.0100 / ch1-600 | cshtml 标签 |
| `string34` | 3 / 0.0100 / ch1-600 | cshtml 标签 |
| `string35` | 3 / 0.0100 / ch1-600 | cshtml 标签 |
| `string36` | 3 / 0.0100 / ch1-600 | cshtml 标签 |
| `string37` | 3 / 0.0100 / ch1-600 | cshtml 标签 |
| `string38` | 3 / 0.0100 / ch1-600 | cshtml 标签 |
| `string39` | 3 / 0.0100 / ch1-600 | cshtml 标签 |
| `string41` | 4 / 0.0150 / ch2-550 | cshtml 标签 |
| `string42` | 4 / 0.0150 / ch2-550 | cshtml 标签 |
| `string43` | 4 / 0.0150 / ch2-550 | cshtml 标签 |
| `string44` | 4 / 0.0150 / ch2-550 | cshtml 标签 |
| `string45` | 4 / 0.0150 / ch2-550 | cshtml 标签 |
| `string46` | 4 / 0.0150 / ch2-550 | cshtml 标签 |
| `string47` | 4 / 0.0150 / ch2-550 | cshtml 标签 |
| `string48` | 4 / 0.0150 / ch2-550 | cshtml 标签 |
| `string49` | 4 / 0.0150 / ch2-550 | cshtml 标签 |
| `string51` | 5 / 0.0200 / ch2-600 | cshtml 标签 |
| `string52` | 5 / 0.0200 / ch2-600 | cshtml 标签 |
| `string53` | 5 / 0.0200 / ch2-600 | cshtml 标签 |
| `string54` | 5 / 0.0200 / ch2-600 | cshtml 标签 |
| `string55` | 5 / 0.0200 / ch2-600 | cshtml 标签 |
| `string56` | 5 / 0.0200 / ch2-600 | cshtml 标签 |
| `string57` | 5 / 0.0200 / ch2-600 | cshtml 标签 |
| `string58` | 5 / 0.0200 / ch2-600 | cshtml 标签 |
| `string59` | 5 / 0.0200 / ch2-600 | cshtml 标签 |
| `string60` | ch2-550 / ch2-600 | cshtml 标签 |
| `string61` | ch2-550 / ch2-600 | cshtml 标签 |
| `string62` | ch2-550 / ch2-600 | cshtml 标签 |
| `string63` | ch2-550 / ch2-600 | cshtml 标签 |
| `string64` | ch2-550 / ch2-600 | cshtml 标签 |
| `string65` | ch2-550 / ch2-600 | cshtml 标签 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string4`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string46`=required；`string47`=required；`string48`=required；`string49`=required；`string5`=required；`string50`=required；`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required；`string56`=required；`string57`=required；`string58`=required；`string59`=required；`string6`=required；`string60`=required；`string61`=required；`string62`=required；`string63`=required；`string64`=required；`string65`=required；`string7`=required


## Sup_RF_Week_NMHCQC（sup_rf_common）
- 《组分仪器工单规则》：光化学组分/甲烷非甲烷.docx
- 源码依据：实体 `Sup_RF_Week_NMHCQC`、视图 `Sup_RF_Week_NMHCQC.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：定值日期 / 有效期至） | 实体注释 |
| `time2` | 结束时间（视图标签：定值日期 / 有效期至） | 实体注释 |
| `time3` | 零气流量计 | cshtml 标签 |
| `time4` | 零气流量计 | cshtml 标签 |
| `string1` | 定值日期 / 有效期至 | cshtml 标签 |
| `string2` | 定值日期 / 有效期至 | cshtml 标签 |
| `string3` | 定值日期 / 有效期至 | cshtml 标签 |
| `string4` | 定值日期 / 有效期至 | cshtml 标签 |
| `string5` | 零气流量计 | cshtml 标签 |
| `string6` | 零气流量计 | cshtml 标签 |
| `string7` | 零气流量计 | cshtml 标签 |
| `string8` | 零气流量计 | cshtml 标签 |
| `string9` | 标气流量计 | cshtml 标签 |
| `string10` | 标气流量计 | cshtml 标签 |
| `string47` | 甲烷峰面积 / 非甲烷总烃/总烃 | cshtml 标签 |
| `string48` | 甲烷峰面积 / 非甲烷总烃/总烃 | cshtml 标签 |


## Sup_RF_Week_RadiationRecord（sup_rf_week_radiationrecord）
- 《组分仪器工单规则》：颗粒物组分/太阳总辐射.docx
- 源码依据：实体 `Sup_RF_Week_RadiationRecord`、视图 `Sup_RF_Week_RadiationRecord.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `radio1` | 1 / 仪器状态 | cshtml 标签 |
| `radio2` | 2 / 表面护罩清洁 | cshtml 标签 |
| `radio3` | 3 / 气泡水准仪 | cshtml 标签 |
| `radio4` | 4 / 安装支架 | cshtml 标签 |
| `radio5` | 5 / 数模转换器（232转485） | cshtml 标签 |
| `radio6` | 6 / 电源适配器 | cshtml 标签 |
| `radio7` | 7 / 数据传输情况 | cshtml 标签 |
| `remark1` | 1 / 仪器状态 | cshtml 标签 |
| `remark2` | 2 / 表面护罩清洁 | cshtml 标签 |
| `remark3` | 3 / 气泡水准仪 | cshtml 标签 |
| `remark4` | 4 / 安装支架 | cshtml 标签 |
| `remark5` | 5 / 数模转换器（232转485） | cshtml 标签 |
| `remark6` | 6 / 电源适配器 | cshtml 标签 |
| `remark7` | 7 / 数据传输情况 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_Week_RadiationRecord_Radiometer.vue）：**

bool_1 至 bool_7 为七项巡检结果（true = 原表 0，正常/执行；false = 原表 1，异常/未执行）； remark 至 remark6 为对应巡检备注；remark7 为总备注；commonFile 为附件。


## Sup_RF_Week_THLiDAR（sup_rf_common）
- 源码依据：实体 `Sup_RF_Week_THLiDAR`、视图 `Sup_RF_Week_THLiDAR.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `bool_1` | 边界层大气成分二维高光谱扫描与分析仪 / 数据采集是否正常 | cshtml 标签 |
| `bool_2` | 镜头是否干净 | cshtml 标签 |
| `bool_3` | 供电是否正常 | cshtml 标签 |
| `bool_4` | 激光器检查 / 激光器能量是否正常 | cshtml 标签 |
| `bool_5` | 激光是否正常出光 | cshtml 标签 |
| `bool_6` | 激光光斑光强密度分布均匀 | cshtml 标签 |
| `bool_7` | 激光光斑是否位于天窗玻璃中心位置 | cshtml 标签 |
| `bool_8` | 采集软件检查 / 软件是否运行正常无报警、死机 | cshtml 标签 |
| `bool_9` | 设备信息状态是否都正常 | cshtml 标签 |
| `bool_10` | 回波信号曲线是否正常 | cshtml 标签 |
| `bool_11` | 信号噪声是否正常 | cshtml 标签 |
| `bool_12` | 分析软件检查 / 软件是否运行正常无报警、死机 | cshtml 标签 |
| `bool_13` | 伪彩图、廓线图展示是否正常 | cshtml 标签 |
| `bool_14` | 自动出图是否正常 | cshtml 标签 |
| `bool_15` | 光机镜片清洁 / 用擦镜布或擦镜纸蘸酒精后将光机镜片表面灰尘及水渍擦拭干净，镜片表面无灰尘凝结无明显水渍 | cshtml 标签 |
| `bool_16` | 天窗镜片清洁 / 用布或餐巾纸蘸水或酒精对天窗镜片表面的灰尘及水渍擦拭干净，玻璃表面无明显灰尘凝结和水渍 | cshtml 标签 |
| `bool_17` | 站房清洁 / 清洁地面灰尘、清理蜘蛛网、清理垃圾。 | cshtml 标签 |
| `remark1` | 异常项目描述 | cshtml 标签 |
| `remark2` | 异常项目处理 | cshtml 标签 |
| `remark3` | 处理结果 | cshtml 标签 |
| `remark4` | 备注描述 | cshtml 标签 |
| `remark5` | 备注描述 | cshtml 标签 |
| `remark6` | 备注描述 | cshtml 标签 |


## Sup_RF_Week_TrafficFlowCheck（sup_rf_common）
- 《组分仪器工单规则》：（交通站，RAR 外）
- 源码依据：实体 `Sup_RF_Week_TrafficFlowCheck`、视图 `Sup_RF_Week_TrafficFlowCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间 | 实体注释 |
| `time2` | 结束时间 | 实体注释 |
| `bool_1` | 软件是否正常： | cshtml 标签 |
| `bool_2` | 周边环境对摄像头是否有影响： | cshtml 标签 |
| `bool_3` | 摄像头是否是挂在大马路的横杠上： | cshtml 标签 |


## Sup_RF_Week_YT_Check（sup_rf_common）
- 源码依据：实体 `Sup_RF_Week_YT_Check`、视图 `Sup_RF_Week_YT_Check.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次校准日期 | 实体注释 |
| `time2` | 参考流量计 - 下一次校准日期 | 实体注释 |
| `time3` | OCEC分析仪资料 - 上一次校准时间 | 实体注释 |
| `time4` | OCEC分析仪资料 - 下一次校准时间 | 实体注释 |
| `remark1` | 1 / 系统状态及参数 / 仪器状态是否正常、有无报警 / / | cshtml 标签 |
| `remark2` | 2 / FID信号是否正常、基线是否稳定 / / | cshtml 标签 |
| `remark3` | 3 / 数据采集及上传数据是否一致 / / | cshtml 标签 |
| `remark4` | 4 / 空压机是否正常工作 / / | cshtml 标签 |
| `remark5` | 5 / 氢气发生器是否正常工作 / / | cshtml 标签 |
| `remark6` | 6 / 采样支管是否凝水、干净 / / | cshtml 标签 |
| `remark7` | 7 / 采样总管风机及加热是否正常 / / | cshtml 标签 |
| `remark8` | 8 / 零气发生器加热温度 / 450℃ | cshtml 标签 |
| `remark9` | 9 / FID检测器温度 / 160℃ | cshtml 标签 |
| `string1` | 设备型号 | 实体注释 |
| `string2` | 出厂编号 | 实体注释 |
| `string3` | 斜率 | 实体注释 |
| `string4` | 截距 | 实体注释 |
| `string5` | 相关系数 | 实体注释 |
| `string6` | 仪器型号 | 实体注释 |
| `string7` | 出厂编号 | 实体注释 |
| `string8` | 监测项目 | 实体注释 |
| `string9` | 设定流量 - 氦气 | 实体注释 |
| `remark10` | 10 / 氢气输出压力 / 不低于0.35Mpa（50psi） | cshtml 标签 |
| `remark11` | 11 / 零气输出压力 / 不低于0.35Mpa（50psi） | cshtml 标签 |
| `remark12` | 12 / 空压机输出压力 / 不低于0.35Mpa（50psi） | cshtml 标签 |
| `remark13` | 13 / 载气稳压阀压力 / 0.25Mpa | cshtml 标签 |
| `remark14` | 14 / 系统维护 / 氢气发生器分子筛\变色硅胶 / 三个月或变色换 | cshtml 标签 |
| `remark15` | 15 / 氢气发生器纯水 / 按需加 | cshtml 标签 |
| `remark16` | 16 / 零气发生器分子筛\变色硅胶 / 三个月或变色换 | cshtml 标签 |
| `remark17` | 17 / 过滤器 / 半年或系统采样流达到设定值更换 | cshtml 标签 |
| `string10` | 显示流量 - 氦气 | 实体注释 |
| `string11` | 参考流量计读数 - 氦气 | 实体注释 |
| `string12` | 参考流量计修正 - 氦气 | 实体注释 |
| `string13` | 误差 - 氦气 | 实体注释 |
| `string14` | 检查结果 - 氦气 | 实体注释 |
| `string15` | 设定流量 - 氦气（吹扫） | 实体注释 |
| `string16` | 显示流量 - 氦气（吹扫） | 实体注释 |
| `string17` | 参考流量计读数 - 氦气（吹扫） | 实体注释 |
| `string18` | 参考流量计修正 - 氦气（吹扫） | 实体注释 |
| `string19` | 误差 - 氦气（吹扫） | 实体注释 |
| `string20` | 检查结果 - 氦气（吹扫） | 实体注释 |
| `string21` | 设定流量 - 氦氧 | 实体注释 |
| `string22` | 显示流量 - 氦氧 | 实体注释 |
| `string23` | 参考流量计读数 - 氦氧 | 实体注释 |
| `string24` | 参考流量计修正 - 氦氧 | 实体注释 |
| `string25` | 误差 - 氦氧 | 实体注释 |
| `string26` | 检查结果 - 氦氧 | 实体注释 |
| `string27` | 设定流量 - 氦甲烷 | 实体注释 |
| `string28` | 显示流量 - 氦甲烷 | 实体注释 |
| `string29` | 参考流量计读数 - 氦甲烷 | 实体注释 |
| `string30` | 参考流量计修正 - 氦甲烷 | 实体注释 |
| `string31` | 误差 - 氦甲烷 | 实体注释 |
| `string32` | 检查结果 - 氦甲烷 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |


## Sup_RF_Week_YT_SingleQC（sup_rf_common）
- 源码依据：实体 `Sup_RF_Week_YT_SingleQC`、视图 `Sup_RF_Week_YT_SingleQC.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次校准日期（视图标签：标准化合物数量 / 有效期） | 实体注释 |
| `time2` | 参考流量计 - 下一次校准日期（视图标签：开始时间 / 结束时间） | 实体注释 |
| `time3` | OCEC分析仪资料 - 上一次校准时间（视图标签：开始时间 / 结束时间） | 实体注释 |
| `time4` | OCEC分析仪资料 - 下一次校准时间 | 实体注释 |
| `string1` | 设备型号（视图标签：多点校准仪型号 / 多点校准仪编号） | 实体注释 |
| `string2` | 出厂编号（视图标签：多点校准仪型号 / 多点校准仪编号） | 实体注释 |
| `string3` | 斜率（视图标签：零气发生器型号 / 零气发生器编号） | 实体注释 |
| `string4` | 截距（视图标签：零气发生器型号 / 零气发生器编号） | 实体注释 |
| `string5` | 相关系数（视图标签：标准气名称 / 标准气编号） | 实体注释 |
| `string6` | 仪器型号（视图标签：标准气名称 / 标准气编号） | 实体注释 |
| `string7` | 出厂编号（视图标签：标准化合物数量 / 有效期） | 实体注释 |
| `string8` | 监测项目（视图标签：室内温湿度及气压） | 实体注释 |
| `string9` | 设定流量 - 氦气（视图标签：室内温湿度及气压） | 实体注释 |
| `string10` | 显示流量 - 氦气（视图标签：室内温湿度及气压） | 实体注释 |
| `string11` | 参考流量计读数 - 氦气（视图标签：记录人） | 实体注释 |
| `string12` | 参考流量计修正 - 氦气（视图标签：1 / 甲烷 / <50ppb / <±10%） | 实体注释 |
| `string13` | 误差 - 氦气（视图标签：1 / 甲烷 / <50ppb / <±10%） | 实体注释 |
| `string14` | 检查结果 - 氦气（视图标签：1 / 甲烷 / <50ppb / <±10%） | 实体注释 |
| `string15` | 设定流量 - 氦气（吹扫）（视图标签：1 / 甲烷 / <50ppb / <±10%） | 实体注释 |
| `string16` | 显示流量 - 氦气（吹扫）（视图标签：2 / 非甲烷总烃（以丙烷计） / <20ppbC / <±10%） | 实体注释 |
| `string17` | 参考流量计读数 - 氦气（吹扫）（视图标签：2 / 非甲烷总烃（以丙烷计） / <20ppbC / <±10%） | 实体注释 |
| `string18` | 参考流量计修正 - 氦气（吹扫）（视图标签：2 / 非甲烷总烃（以丙烷计） / <20ppbC / <±10%） | 实体注释 |
| `string19` | 误差 - 氦气（吹扫）（视图标签：2 / 非甲烷总烃（以丙烷计） / <20ppbC / <±10%） | 实体注释 |
| `string20` | 检查结果 - 氦气（吹扫）（视图标签：零气空白结论 / 单点标气结论） | 实体注释 |
| `string21` | 设定流量 - 氦氧（视图标签：零气空白结论 / 单点标气结论） | 实体注释 |
| `string22` | 显示流量 - 氦氧 | 实体注释 |
| `string23` | 参考流量计读数 - 氦氧 | 实体注释 |
| `string24` | 参考流量计修正 - 氦氧 | 实体注释 |
| `string25` | 误差 - 氦氧 | 实体注释 |
| `string26` | 检查结果 - 氦氧 | 实体注释 |
| `string27` | 设定流量 - 氦甲烷 | 实体注释 |
| `string28` | 显示流量 - 氦甲烷 | 实体注释 |
| `string29` | 参考流量计读数 - 氦甲烷 | 实体注释 |
| `string30` | 参考流量计修正 - 氦甲烷 | 实体注释 |
| `string31` | 误差 - 氦甲烷 | 实体注释 |
| `string32` | 检查结果 - 氦甲烷 | 实体注释 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_WholeDiaphargmCalibration（sup_rf_common）
- 源码依据：实体 `Sup_RF_WholeDiaphargmCalibration`、视图 `Sup_RF_WholeDiaphargmCalibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 重金属分析仪资料上一次核查日期（视图标签：PM2.5中重金属） | 实体注释 |
| `time2` | 重金属分析仪资料下一次核查日期（视图标签：PM2.5中重金属） | 实体注释 |
| `string1` | 室内温度（视图标签：温度 / 湿度） | 实体注释 |
| `string2` | 室内湿度（视图标签：温度 / 湿度） | 实体注释 |
| `string3` | 仪器型号（视图标签：PM2.5中重金属） | 实体注释 |
| `string4` | 出厂编号（视图标签：PM2.5中重金属） | 实体注释 |
| `string5` | 1 / Al | cshtml 标签 |
| `string6` | 1 / Al | cshtml 标签 |
| `string7` | 1 / Al | cshtml 标签 |
| `string8` | 1 / Al | cshtml 标签 |
| `string9` | 2 / Si | cshtml 标签 |
| `string10` | 2 / Si | cshtml 标签 |
| `string11` | 2 / Si | cshtml 标签 |
| `string12` | 2 / Si | cshtml 标签 |
| `string13` | 3 / P | cshtml 标签 |
| `string14` | 3 / P | cshtml 标签 |
| `string15` | 3 / P | cshtml 标签 |
| `string16` | 3 / P | cshtml 标签 |
| `string17` | 4 / S | cshtml 标签 |
| `string18` | 4 / S | cshtml 标签 |
| `string19` | 4 / S | cshtml 标签 |
| `string20` | 4 / S | cshtml 标签 |
| `string21` | 5 / K | cshtml 标签 |
| `string22` | 5 / K | cshtml 标签 |
| `string23` | 5 / K | cshtml 标签 |
| `string24` | 5 / K | cshtml 标签 |
| `string25` | 6 / Ca | cshtml 标签 |
| `string26` | 6 / Ca | cshtml 标签 |
| `string27` | 6 / Ca | cshtml 标签 |
| `string28` | 6 / Ca | cshtml 标签 |
| `string29` | 7 / Ti | cshtml 标签 |
| `string30` | 7 / Ti | cshtml 标签 |
| `string31` | 7 / Ti | cshtml 标签 |
| `string32` | 7 / Ti | cshtml 标签 |
| `string33` | 8 / Sc | cshtml 标签 |
| `string34` | 8 / Sc | cshtml 标签 |
| `string35` | 8 / Sc | cshtml 标签 |
| `string36` | 8 / Sc | cshtml 标签 |
| `string37` | 9 / V | cshtml 标签 |
| `string38` | 9 / V | cshtml 标签 |
| `string39` | 9 / V | cshtml 标签 |
| `string40` | 9 / V | cshtml 标签 |
| `string41` | 10 / Cr | cshtml 标签 |
| `string42` | 10 / Cr | cshtml 标签 |
| `string43` | 10 / Cr | cshtml 标签 |
| `string44` | 10 / Cr | cshtml 标签 |
| `string45` | 11 / Fe | cshtml 标签 |
| `string46` | 11 / Fe | cshtml 标签 |
| `string47` | 11 / Fe | cshtml 标签 |
| `string48` | 11 / Fe | cshtml 标签 |
| `string49` | 12 / Mn | cshtml 标签 |
| `string50` | 12 / Mn | cshtml 标签 |
| `string51` | 12 / Mn | cshtml 标签 |
| `string52` | 12 / Mn | cshtml 标签 |
| `string53` | 13 / Cl | cshtml 标签 |
| `string54` | 13 / Cl | cshtml 标签 |
| `string55` | 13 / Cl | cshtml 标签 |
| `string56` | 13 / Cl | cshtml 标签 |
| `string57` | 14 / Cs | cshtml 标签 |
| `string58` | 14 / Cs | cshtml 标签 |
| `string59` | 14 / Cs | cshtml 标签 |
| `string60` | 14 / Cs | cshtml 标签 |
| `string61` | 15 / Ar | cshtml 标签 |
| `string62` | 15 / Ar | cshtml 标签 |
| `string63` | 15 / Ar | cshtml 标签 |
| `string64` | 15 / Ar | cshtml 标签 |
| `string65` | 16 / Ba | cshtml 标签 |
| `string66` | 16 / Ba | cshtml 标签 |
| `string67` | 16 / Ba | cshtml 标签 |
| `string68` | 16 / Ba | cshtml 标签 |
| `string69` | 17 / Co | cshtml 标签 |
| `string70` | 17 / Co | cshtml 标签 |
| `string71` | 17 / Co | cshtml 标签 |
| `string72` | 17 / Co | cshtml 标签 |
| `string73` | 18 / Ni | cshtml 标签 |
| `string74` | 18 / Ni | cshtml 标签 |
| `string75` | 18 / Ni | cshtml 标签 |
| `string76` | 18 / Ni | cshtml 标签 |
| `string77` | 19 / Cu | cshtml 标签 |
| `string78` | 19 / Cu | cshtml 标签 |
| `string79` | 19 / Cu | cshtml 标签 |
| `string80` | 19 / Cu | cshtml 标签 |
| `string81` | 20 / Zn | cshtml 标签 |
| `string82` | 20 / Zn | cshtml 标签 |
| `string83` | 20 / Zn | cshtml 标签 |
| `string84` | 20 / Zn | cshtml 标签 |
| `string85` | 21 / Ga | cshtml 标签 |
| `string86` | 21 / Ga | cshtml 标签 |
| `string87` | 21 / Ga | cshtml 标签 |
| `string88` | 21 / Ga | cshtml 标签 |
| `string89` | 22 / As | cshtml 标签 |
| `string90` | 22 / As | cshtml 标签 |
| `string91` | 22 / As | cshtml 标签 |
| `string92` | 22 / As | cshtml 标签 |
| `string93` | 23 / Se | cshtml 标签 |
| `string94` | 23 / Se | cshtml 标签 |
| `string95` | 23 / Se | cshtml 标签 |
| `string96` | 23 / Se | cshtml 标签 |
| `string97` | 24 / Br | cshtml 标签 |
| `string98` | 24 / Br | cshtml 标签 |
| `string99` | 24 / Br | cshtml 标签 |
| `string100` | 24 / Br | cshtml 标签 |
| `string101` | 25 / Sr | cshtml 标签 |
| `string102` | 25 / Sr | cshtml 标签 |
| `string103` | 25 / Sr | cshtml 标签 |
| `string104` | 25 / Sr | cshtml 标签 |
| `string105` | 26 / Mo | cshtml 标签 |
| `string106` | 26 / Mo | cshtml 标签 |
| `string107` | 26 / Mo | cshtml 标签 |
| `string108` | 26 / Mo | cshtml 标签 |
| `string109` | 27 / Hg | cshtml 标签 |
| `string110` | 27 / Hg | cshtml 标签 |
| `string111` | 27 / Hg | cshtml 标签 |
| `string112` | 27 / Hg | cshtml 标签 |
| `string113` | 28 / Tl | cshtml 标签 |
| `string114` | 28 / Tl | cshtml 标签 |
| `string115` | 28 / Tl | cshtml 标签 |
| `string116` | 28 / Tl | cshtml 标签 |
| `string117` | 29 / Pb | cshtml 标签 |
| `string118` | 29 / Pb | cshtml 标签 |
| `string119` | 29 / Pb | cshtml 标签 |
| `string120` | 29 / Pb | cshtml 标签 |
| `string121` | 30 / Pd | cshtml 标签 |
| `string122` | 30 / Pd | cshtml 标签 |
| `string123` | 30 / Pd | cshtml 标签 |
| `string124` | 30 / Pd | cshtml 标签 |
| `string125` | 31 / Ag | cshtml 标签 |
| `string126` | 31 / Ag | cshtml 标签 |
| `string127` | 31 / Ag | cshtml 标签 |
| `string128` | 31 / Ag | cshtml 标签 |
| `string129` | 32 / Cd | cshtml 标签 |
| `string130` | 32 / Cd | cshtml 标签 |
| `string131` | 32 / Cd | cshtml 标签 |
| `string132` | 32 / Cd | cshtml 标签 |
| `string133` | 33 / Sn | cshtml 标签 |
| `string134` | 33 / Sn | cshtml 标签 |
| `string135` | 33 / Sn | cshtml 标签 |
| `string136` | 33 / Sn | cshtml 标签 |
| `string137` | 34 / Sb | cshtml 标签 |
| `string138` | 34 / Sb | cshtml 标签 |
| `string139` | 34 / Sb | cshtml 标签 |
| `string140` | 34 / Sb | cshtml 标签 |
| `string141` | 35 / Te | cshtml 标签 |
| `string142` | 35 / Te | cshtml 标签 |
| `string143` | 35 / Te | cshtml 标签 |
| `string144` | 35 / Te | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string100`=required；`string101`=required；`string102`=required；`string103`=required；`string104`=required；`string105`=required；`string106`=required；`string107`=required；`string108`=required；`string109`=required；`string11`=required；`string110`=required；`string111`=required；`string112`=required；`string113`=required；`string114`=required；`string115`=required；`string116`=required；`string117`=required；`string118`=required；`string119`=required；`string12`=required；`string120`=required；`string121`=required；`string122`=required；`string123`=required；`string124`=required；`string125`=required；`string126`=required；`string127`=required；`string128`=required；`string129`=required；`string13`=required；`string130`=required；`string131`=required；`string132`=required；`string133`=required；`string134`=required；`string135`=required；`string136`=required；`string137`=required；`string138`=required；`string139`=required；`string14`=required；`string140`=required；`string141`=required；`string142`=required；`string143`=required；`string144`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string4`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string46`=required；`string47`=required；`string48`=required；`string49`=required；`string5`=required；`string50`=required；`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required；`string56`=required；`string57`=required；`string58`=required；`string59`=required；`string6`=required；`string60`=required；`string61`=required；`string62`=required；`string63`=required；`string64`=required；`string65`=required；`string66`=required；`string67`=required；`string68`=required；`string69`=required；`string7`=required；`string70`=required；`string71`=required；`string72`=required；`string73`=required；`string74`=required；`string75`=required；`string76`=required；`string77`=required；`string78`=required；`string79`=required；`string8`=required；`string80`=required；`string81`=required；`string82`=required；`string83`=required；`string84`=required；`string85`=required；`string86`=required；`string87`=required；`string88`=required；`string89`=required；`string9`=required；`string90`=required；`string91`=required；`string92`=required；`string93`=required；`string94`=required；`string95`=required；`string96`=required；`string97`=required；`string98`=required；`string99`=required


## Sup_RF_Year_HONOCheck（sup_rf_common）
- 《组分仪器工单规则》：颗粒物组分/HONO.docx
- 源码依据：实体 `Sup_RF_Year_HONOCheck`、视图 `Sup_RF_Year_HONOCheck.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 开始时间（视图标签：维护单位 / 安装地点 / 维护时间） | 实体注释 |
| `time2` | 结束时间（视图标签：有效期限 / 标准溶液配置记录编号） | 实体注释 |
| `bool_1` | 1 / 室外检查 / 室外取气盒固定是否牢固 | cshtml 标签 |
| `bool_2` | 循环水浴器温控及水位高度 | cshtml 标签 |
| `bool_3` | 取气盒循环水运行检查 | cshtml 标签 |
| `bool_4` | 取气盒管路连接 | cshtml 标签 |
| `bool_5` | 2 / 系统检查 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `bool_6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `bool_7` | 泵头转速是否正常 | cshtml 标签 |
| `bool_8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `bool_9` | 泵管卡子松紧度 | cshtml 标签 |
| `bool_10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `bool_11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `bool_12` | 安全瓶 / 无进液 | cshtml 标签 |
| `bool_13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `bool_14` | 光源LED / 正常光照 | cshtml 标签 |
| `bool_15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `bool_16` | 红色线是否达到预计值 | cshtml 标签 |
| `bool_17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `bool_18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `bool_19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `bool_20` | 测量数据偏离 | cshtml 标签 |
| `bool_21` | 是否存在异常数据 | cshtml 标签 |
| `bool_22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `bool_23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `bool_24` | R2避光保护 | cshtml 标签 |
| `bool_25` | 外表无破损 | cshtml 标签 |
| `bool_26` | 试剂 / 是否过期 | cshtml 标签 |
| `bool_27` | 配置是否准确 | cshtml 标签 |
| `bool_28` | 剩余量是否充足 | cshtml 标签 |
| `bool_29` | 空气过滤膜 / 检查是否需要更换 | cshtml 标签 |
| `remark1` | 1 / 室外检查 / 室外取气盒固定是否牢固 | cshtml 标签 |
| `remark2` | 循环水浴器温控及水位高度 | cshtml 标签 |
| `remark3` | 取气盒循环水运行检查 | cshtml 标签 |
| `remark4` | 取气盒管路连接 | cshtml 标签 |
| `remark5` | 2 / 系统检查 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `remark6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `remark7` | 泵头转速是否正常 | cshtml 标签 |
| `remark8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `remark9` | 泵管卡子松紧度 | cshtml 标签 |
| `string1` | 1 / 室外检查 / 室外取气盒固定是否牢固 | cshtml 标签 |
| `string2` | 循环水浴器温控及水位高度 | cshtml 标签 |
| `string3` | 取气盒循环水运行检查 | cshtml 标签 |
| `string4` | 取气盒管路连接 | cshtml 标签 |
| `string5` | 2 / 系统检查 / 主机 / 前面板显示控制是否正常 | cshtml 标签 |
| `string6` | 蠕动泵 / 泵管堵塞、接头松紧度 | cshtml 标签 |
| `string7` | 泵头转速是否正常 | cshtml 标签 |
| `string8` | 检查蠕动泵管是否需要更换 | cshtml 标签 |
| `string9` | 泵管卡子松紧度 | cshtml 标签 |
| `remark10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `remark11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `remark12` | 安全瓶 / 无进液 | cshtml 标签 |
| `remark13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `remark14` | 光源LED / 正常光照 | cshtml 标签 |
| `remark15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `remark16` | 红色线是否达到预计值 | cshtml 标签 |
| `remark17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `remark18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `remark19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `remark20` | 测量数据偏离 | cshtml 标签 |
| `remark21` | 是否存在异常数据 | cshtml 标签 |
| `remark22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `remark23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `remark24` | R2避光保护 | cshtml 标签 |
| `remark25` | 外表无破损 | cshtml 标签 |
| `remark26` | 试剂 / 是否过期 | cshtml 标签 |
| `remark27` | 配置是否准确 | cshtml 标签 |
| `remark28` | 剩余量是否充足 | cshtml 标签 |
| `remark29` | 空气过滤膜 / 检查是否需要更换 | cshtml 标签 |
| `remark49` | 异常问题处理记录： | cshtml 标签 |
| `remark50` | 备注： | cshtml 标签 |
| `string10` | 内部液路管 / 松紧度、有无漏液 | cshtml 标签 |
| `string11` | 空气泵 / 正常运转、无异常声响 | cshtml 标签 |
| `string12` | 安全瓶 / 无进液 | cshtml 标签 |
| `string13` | 光纤 / 外观无折损、接头无松动 | cshtml 标签 |
| `string14` | 光源LED / 正常光照 | cshtml 标签 |
| `string15` | 分析软件 / 光谱强度 / 蓝色线是否达到预计值 | cshtml 标签 |
| `string16` | 红色线是否达到预计值 | cshtml 标签 |
| `string17` | 吸光度强度 / 吸光度强度有无异常峰 | cshtml 标签 |
| `string18` | 吸光度强度是否在合理范围 | cshtml 标签 |
| `string19` | 数据质控 / 测量数据有无异常 | cshtml 标签 |
| `string20` | 测量数据偏离 | cshtml 标签 |
| `string21` | 是否存在异常数据 | cshtml 标签 |
| `string22` | 数据存储 / 是否正常存入对应文件夹 | cshtml 标签 |
| `string23` | 3 / 试剂检查 / 试剂袋 / 是否泄漏 | cshtml 标签 |
| `string24` | R2避光保护 | cshtml 标签 |
| `string25` | 外表无破损 | cshtml 标签 |
| `string26` | 试剂 / 是否过期 | cshtml 标签 |
| `string27` | 配置是否准确 | cshtml 标签 |
| `string28` | 剩余量是否充足 | cshtml 标签 |
| `string29` | 空气过滤膜 / 检查是否需要更换 | cshtml 标签 |
| `string51` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string52` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string53` | 设备名称 / 设备型号 / 维护人 | cshtml 标签 |
| `string54` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string55` | 维护单位 / 安装地点 / 维护时间 | cshtml 标签 |
| `string56` | 有效期限 / 标准溶液配置记录编号 | cshtml 标签 |
| `string57` | 有效期限 / 标准溶液配置记录编号 | cshtml 标签 |
| `string58` | 有效期限 / 标准溶液配置记录编号 | cshtml 标签 |
| `string59` | 有效期限 / 标准溶液配置记录编号 | cshtml 标签 |
| `string60` | 采样时间（min） / HONO浓度 （nmol/mol） | cshtml 标签 |
| `string61` | 采样时间（min） / HONO浓度 （nmol/mol） | cshtml 标签 |
| `string62` | 采样时间（min） / HONO浓度 （nmol/mol） | cshtml 标签 |
| `string63` | 采样时间（min） / HONO浓度 （nmol/mol） | cshtml 标签 |
| `string64` | 零点 | cshtml 标签 |
| `string65` | 零点 | cshtml 标签 |
| `string66` | 零点 | cshtml 标签 |
| `string67` | 零点 | cshtml 标签 |
| `string68` | 1 | cshtml 标签 |
| `string69` | 1 | cshtml 标签 |
| `string70` | 1 | cshtml 标签 |
| `string71` | 1 | cshtml 标签 |
| `string72` | 2 | cshtml 标签 |
| `string73` | 2 | cshtml 标签 |
| `string74` | 2 | cshtml 标签 |
| `string75` | 2 | cshtml 标签 |
| `string76` | 3 | cshtml 标签 |
| `string77` | 3 | cshtml 标签 |
| `string78` | 3 | cshtml 标签 |
| `string79` | 3 | cshtml 标签 |
| `string80` | 4 | cshtml 标签 |
| `string81` | 4 | cshtml 标签 |
| `string82` | 4 | cshtml 标签 |
| `string83` | 4 | cshtml 标签 |
| `string84` | 5 | cshtml 标签 |
| `string85` | 5 | cshtml 标签 |
| `string86` | 5 | cshtml 标签 |
| `string87` | 5 | cshtml 标签 |
| `string88` | 6 | cshtml 标签 |
| `string89` | 6 | cshtml 标签 |
| `string90` | 6 | cshtml 标签 |
| `string91` | 6 | cshtml 标签 |
| `string92` | 精密度 | cshtml 标签 |
| `string93` | 精密度 | cshtml 标签 |
| `string94` | 精密度 | cshtml 标签 |
| `string95` | 精密度 | cshtml 标签 |

**平台校验器：**`string51`=required；`string52`=required；`string53`=required；`string54`=required；`string55`=required；`string68`=required；`string69`=required；`string70`=required；`string71`=required；`string72`=required；`string73`=required；`string74`=required；`string75`=required；`string76`=required；`string77`=required；`string78`=required；`string79`=required；`string80`=required；`string81`=required；`string82`=required；`string83`=required；`string84`=required；`string85`=required；`string86`=required；`string87`=required；`string88`=required；`string89`=required；`string90`=required；`string91`=required


## Sup_RF_Year_RadiationCalibration（sup_rf_year_radiationcalibration）
- 《组分仪器工单规则》：颗粒物组分/太阳总辐射.docx
- 源码依据：实体 `Sup_RF_Year_RadiationCalibration`、视图 `Sup_RF_Year_RadiationCalibration.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 上一次 / 下一次 | cshtml 标签 |
| `time2` | 上一次 / 下一次 | cshtml 标签 |
| `time3` | 上次校准日期 / 下次校准日期 | cshtml 标签 |
| `time4` | 上次校准日期 / 下次校准日期 | cshtml 标签 |
| `string1` | 上一次 / 下一次 | cshtml 标签 |
| `string2` | 上一次 / 下一次 | cshtml 标签 |
| `string3` | 上一次 / 下一次 | cshtml 标签 |
| `string4` | 设备型号 / 出厂编号 | cshtml 标签 |
| `string5` | 设备型号 / 出厂编号 | cshtml 标签 |
| `string6` | 测量范围 / 修正因子 | cshtml 标签 |
| `string7` | 测量范围 / 修正因子 | cshtml 标签 |
| `string8` | 校准前 | cshtml 标签 |
| `string9` | 校准前 | cshtml 标签 |
| `string10` | 校准前 | cshtml 标签 |
| `string11` | 校准前 | cshtml 标签 |
| `string12` | 校准前 | cshtml 标签 |
| `string13` | 校准前 | cshtml 标签 |
| `string14` | 校准前 | cshtml 标签 |
| `string15` | 校准前 | cshtml 标签 |
| `string16` | 校准前 | cshtml 标签 |
| `string17` | 校准前 | cshtml 标签 |
| `string18` | 校准前 | cshtml 标签 |
| `string19` | 校准前 | cshtml 标签 |

**Vue 头部字段映射（Sup_RF_Year_RadiationCalibration_Radiometer.vue）：**

 string1 至 string7 为仪器和参考辐射计资料；time1 至 time4 为校准日期； string8 至 string13 为校准前读数，string14 至 string19 为校准后读数；remark 为备注。 string10/string16 为已修正标准值，string11/string17 为偏差，string18 为校准后校准系数。

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_Year_YT_AccuracyRecord（sup_rf_common）
- 源码依据：实体 `Sup_RF_Year_YT_AccuracyRecord`、视图 `Sup_RF_Year_YT_AccuracyRecord.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 参考流量计 - 上一次校准日期（视图标签：甲烷钢瓶气编号 / 甲烷钢瓶气浓度 / 有效期） | 实体注释 |
| `time2` | 参考流量计 - 下一次校准日期（视图标签：丙烷钢瓶气编号 / 丙烷钢瓶气浓度 / 有效期） | 实体注释 |
| `time3` | OCEC分析仪资料 - 上一次校准时间（视图标签：开始时间： / 结束时间：） | 实体注释 |
| `time4` | OCEC分析仪资料 - 下一次校准时间（视图标签：开始时间： / 结束时间：） | 实体注释 |
| `string1` | 设备型号（视图标签：多点校准仪型号 / 多点校准仪编号） | 实体注释 |
| `string2` | 出厂编号（视图标签：多点校准仪型号 / 多点校准仪编号） | 实体注释 |
| `string3` | 斜率（视图标签：零气发生器型号 / 零气发生器编号） | 实体注释 |
| `string4` | 截距（视图标签：零气发生器型号 / 零气发生器编号） | 实体注释 |
| `string5` | 相关系数（视图标签：甲烷钢瓶气编号 / 甲烷钢瓶气浓度 / 有效期） | 实体注释 |
| `string6` | 仪器型号（视图标签：甲烷钢瓶气编号 / 甲烷钢瓶气浓度 / 有效期） | 实体注释 |
| `string7` | 出厂编号（视图标签：丙烷钢瓶气编号 / 丙烷钢瓶气浓度 / 有效期） | 实体注释 |
| `string8` | 监测项目（视图标签：丙烷钢瓶气编号 / 丙烷钢瓶气浓度 / 有效期） | 实体注释 |
| `string9` | 设定流量 - 氦气（视图标签：室内温湿度及气压） | 实体注释 |
| `string10` | 显示流量 - 氦气（视图标签：室内温湿度及气压） | 实体注释 |
| `string11` | 参考流量计读数 - 氦气（视图标签：室内温湿度及气压） | 实体注释 |
| `string12` | 参考流量计修正 - 氦气（视图标签：记录人：） | 实体注释 |
| `string13` | 误差 - 氦气（视图标签：1 / 甲烷 / 20%FS） | 实体注释 |
| `string14` | 检查结果 - 氦气（视图标签：1 / 甲烷 / 20%FS） | 实体注释 |
| `string15` | 设定流量 - 氦气（吹扫）（视图标签：1 / 甲烷 / 20%FS） | 实体注释 |
| `string16` | 显示流量 - 氦气（吹扫）（视图标签：1 / 甲烷 / 20%FS） | 实体注释 |
| `string17` | 参考流量计读数 - 氦气（吹扫）（视图标签：1 / 甲烷 / 20%FS） | 实体注释 |
| `string18` | 参考流量计修正 - 氦气（吹扫）（视图标签：1 / 甲烷 / 20%FS） | 实体注释 |
| `string19` | 误差 - 氦气（吹扫）（视图标签：1 / 甲烷 / 20%FS） | 实体注释 |
| `string20` | 检查结果 - 氦气（吹扫）（视图标签：1 / 甲烷 / 20%FS） | 实体注释 |
| `string21` | 设定流量 - 氦氧（视图标签：1 / 甲烷 / 20%FS） | 实体注释 |
| `string22` | 显示流量 - 氦氧（视图标签：2 / 非甲烷总烃） | 实体注释 |
| `string23` | 参考流量计读数 - 氦氧（视图标签：2 / 非甲烷总烃） | 实体注释 |
| `string24` | 参考流量计修正 - 氦氧（视图标签：2 / 非甲烷总烃） | 实体注释 |
| `string25` | 误差 - 氦氧（视图标签：2 / 非甲烷总烃） | 实体注释 |
| `string26` | 检查结果 - 氦氧（视图标签：2 / 非甲烷总烃） | 实体注释 |
| `string27` | 设定流量 - 氦甲烷（视图标签：2 / 非甲烷总烃） | 实体注释 |
| `string28` | 显示流量 - 氦甲烷（视图标签：2 / 非甲烷总烃） | 实体注释 |
| `string29` | 参考流量计读数 - 氦甲烷（视图标签：2 / 非甲烷总烃） | 实体注释 |
| `string30` | 参考流量计修正 - 氦甲烷（视图标签：2 / 非甲烷总烃） | 实体注释 |
| `string31` | 误差 - 氦甲烷（视图标签：3 / 甲烷 / 80%FS） | 实体注释 |
| `string32` | 检查结果 - 氦甲烷（视图标签：3 / 甲烷 / 80%FS） | 实体注释 |
| `string33` | 3 / 甲烷 / 80%FS | cshtml 标签 |
| `string34` | 3 / 甲烷 / 80%FS | cshtml 标签 |
| `string35` | 3 / 甲烷 / 80%FS | cshtml 标签 |
| `string36` | 3 / 甲烷 / 80%FS | cshtml 标签 |
| `string37` | 3 / 甲烷 / 80%FS | cshtml 标签 |
| `string38` | 3 / 甲烷 / 80%FS | cshtml 标签 |
| `string39` | 3 / 甲烷 / 80%FS | cshtml 标签 |
| `string40` | 4 / 非甲烷总烃 | cshtml 标签 |
| `string41` | 4 / 非甲烷总烃 | cshtml 标签 |
| `string42` | 4 / 非甲烷总烃 | cshtml 标签 |
| `string43` | 4 / 非甲烷总烃 | cshtml 标签 |
| `string44` | 4 / 非甲烷总烃 | cshtml 标签 |
| `string45` | 4 / 非甲烷总烃 | cshtml 标签 |
| `string46` | 4 / 非甲烷总烃 | cshtml 标签 |
| `string47` | 4 / 非甲烷总烃 | cshtml 标签 |
| `string48` | 4 / 非甲烷总烃 | cshtml 标签 |
| `string150` | 数据文件名称 | 实体注释 |

**平台校验器：**`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string27`=required；`string28`=required；`string29`=required；`string3`=required；`string30`=required；`string31`=required；`string32`=required；`string33`=required；`string34`=required；`string35`=required；`string36`=required；`string37`=required；`string38`=required；`string39`=required；`string4`=required；`string40`=required；`string41`=required；`string42`=required；`string43`=required；`string44`=required；`string45`=required；`string46`=required；`string47`=required；`string48`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required


## Sup_RF_ZeroSpanCalibration（sup_rf_zerospancalibration）
- 源码依据：实体 `Sup_RF_ZeroSpanCalibration`、视图 `Sup_RF_ZeroSpanCalibration.cshtml`

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `time1` | 当天第几次 / 时间 | cshtml 标签 |
| `time2` | 添加一行 | cshtml 标签 |
| `time3` | 添加一行 | cshtml 标签 |
| `time4` | （视图绑定，含义见标签） | cshtml 标签 |
| `time5` | （视图绑定，含义见标签） | cshtml 标签 |
| `time6` | （视图绑定，含义见标签） | cshtml 标签 |
| `time7` | （视图绑定，含义见标签） | cshtml 标签 |
| `time8` | （视图绑定，含义见标签） | cshtml 标签 |
| `time9` | （视图绑定，含义见标签） | cshtml 标签 |
| `time10` | （视图绑定，含义见标签） | cshtml 标签 |
| `time11` | （视图绑定，含义见标签） | cshtml 标签 |
| `time12` | （视图绑定，含义见标签） | cshtml 标签 |
| `remarks` | 备注 | cshtml 标签 |
| `zpcone1` | 当天第几次 / 时间 | cshtml 标签 |
| `zpcone2` | 添加一行 | cshtml 标签 |
| `zpcone3` | 添加一行 | cshtml 标签 |
| `zpcone4` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpcone5` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpcone6` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpcone7` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpcone8` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpcone9` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpctwo1` | 当天第几次 / 时间 | cshtml 标签 |
| `zpctwo2` | 添加一行 | cshtml 标签 |
| `zpctwo3` | 添加一行 | cshtml 标签 |
| `zpctwo4` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpctwo5` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpctwo6` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpctwo7` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpctwo8` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpctwo9` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpcone10` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpcone11` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpcone12` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpctwo10` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpctwo11` | （视图绑定，含义见标签） | cshtml 标签 |
| `zpctwo12` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift1` | 当天第几次 / 时间 | cshtml 标签 |
| `spandrift2` | 添加一行 | cshtml 标签 |
| `spandrift3` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift4` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift5` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift6` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift7` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift8` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift9` | （视图绑定，含义见标签） | cshtml 标签 |
| `zerodrift1` | 当天第几次 / 时间 | cshtml 标签 |
| `zerodrift2` | 添加一行 | cshtml 标签 |
| `zerodrift3` | 添加一行 | cshtml 标签 |
| `zerodrift4` | （视图绑定，含义见标签） | cshtml 标签 |
| `zerodrift5` | （视图绑定，含义见标签） | cshtml 标签 |
| `zerodrift6` | （视图绑定，含义见标签） | cshtml 标签 |
| `zerodrift7` | （视图绑定，含义见标签） | cshtml 标签 |
| `zerodrift8` | （视图绑定，含义见标签） | cshtml 标签 |
| `zerodrift9` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift10` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift11` | （视图绑定，含义见标签） | cshtml 标签 |
| `spandrift12` | （视图绑定，含义见标签） | cshtml 标签 |
| `zerodrift10` | （视图绑定，含义见标签） | cshtml 标签 |
| `zerodrift11` | （视图绑定，含义见标签） | cshtml 标签 |
| `zerodrift12` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord1` | 当天第几次 / 时间 | cshtml 标签 |
| `abnormalrecord2` | 添加一行 | cshtml 标签 |
| `abnormalrecord3` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord4` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord5` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord6` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord7` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord8` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord9` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord10` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord11` | （视图绑定，含义见标签） | cshtml 标签 |
| `abnormalrecord12` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration1` | 当天第几次 / 时间 | cshtml 标签 |
| `spancalibration2` | 添加一行 | cshtml 标签 |
| `spancalibration3` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration4` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration5` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration6` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration7` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration8` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration9` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration10` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration11` | （视图绑定，含义见标签） | cshtml 标签 |
| `spancalibration12` | （视图绑定，含义见标签） | cshtml 标签 |

**平台校验器：**`spancalibration1`=double；`spandrift1`=double；`string1`=required；`string10`=required；`string11`=required；`string12`=required；`string13`=required；`string14`=required；`string15`=required；`string16`=required；`string17`=required；`string18`=required；`string19`=required；`string2`=required；`string20`=required；`string21`=required；`string22`=required；`string23`=required；`string24`=required；`string25`=required；`string26`=required；`string3`=required；`string4`=required；`string5`=required；`string6`=required；`string7`=required；`string8`=required；`string9`=required；`zerodrift1`=double；`zpcone1`=integer


## Sup_RF_thybHalfYearMaintain（sup_rf_thybhalfyearmaintain）
- 源码依据：实体 `Sup_RF_thybHalfYearMaintain`、视图 `Sup_RF_thybHalfYearMaintain.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remark_1` | 1 / EI离子源清洗 | cshtml 标签 |
| `remark_2` | 1 / MS灯丝 | cshtml 标签 |
| `remark_3` | 2 / 前级泵泵油检查 | cshtml 标签 |
| `result_1` | 1 / EI离子源清洗 | cshtml 标签 |
| `result_2` | 1 / MS灯丝 | cshtml 标签 |
| `result_3` | 2 / 前级泵泵油检查 | cshtml 标签 |


## Sup_RF_thybMonthMaintain（sup_rf_thybmonthmaintain）
- 源码依据：实体 `Sup_RF_thybMonthMaintain`、视图 `Sup_RF_thybMonthMaintain.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remark_1` | 1 / 冷阱除冰 | cshtml 标签 |
| `remark_2` | 1 / 零气发生器干燥硅胶 | cshtml 标签 |
| `remark_3` | 1 / 仪器调谐 | cshtml 标签 |
| `result_1` | 1 / 冷阱除冰 | cshtml 标签 |
| `result_2` | 1 / 零气发生器干燥硅胶 | cshtml 标签 |
| `result_3` | 1 / 仪器调谐 | cshtml 标签 |
| `checkpoint` | 维护检查（可多选于1项） | cshtml 标签 |


## Sup_RF_thybQuarterMaintain（sup_rf_thybquartermaintain）
- 源码依据：实体 `Sup_RF_thybQuarterMaintain`、视图 `Sup_RF_thybQuarterMaintain.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remark_1` | 1 / 零气发生器维护 | cshtml 标签 |
| `remark_2` | 2 / 氢气发生器维护 | cshtml 标签 |
| `remark_3` | 1 / 活性炭 | cshtml 标签 |
| `remark_4` | 2 / 分子筛 | cshtml 标签 |
| `remark_5` | 3 / 全流程验漏检查 | cshtml 标签 |
| `result_1` | 1 / 零气发生器维护 | cshtml 标签 |
| `result_2` | 2 / 氢气发生器维护 | cshtml 标签 |
| `result_3` | 1 / 活性炭 | cshtml 标签 |
| `result_4` | 2 / 分子筛 | cshtml 标签 |
| `result_5` | 3 / 全流程验漏检查 | cshtml 标签 |


## Sup_RF_thybWeekCheck（sup_rf_common）
- 源码依据：实体 `Sup_RF_thybWeekCheck`、视图 `Sup_RF_thybWeekCheck.cshtml`、Vue 移植版 x1

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `ms_1` | 1 / 仪器状态 | cshtml 标签 |
| `ms_2` | 2 / 空气进样量（400ml） | cshtml 标签 |
| `ms_3` | 3 / 外标进样量（200ml） | cshtml 标签 |
| `ms_4` | 4 / 内标进样量（90ml） | cshtml 标签 |
| `ms_7` | 7 / 除水阱温度（℃） | cshtml 标签 |
| `ms_9` | 1 / 仪器状态 | cshtml 标签 |
| `fid_1` | 1 / 仪器状态 | cshtml 标签 |
| `fid_2` | 2 / 空气进样量（400ml） | cshtml 标签 |
| `fid_3` | 3 / 外标进样量（200ml） | cshtml 标签 |
| `fid_5` | 5 / TH-300软件运行情况 | cshtml 标签 |
| `fid_6` | 6 / 捕集阱温度（小于-150℃） | cshtml 标签 |
| `fid_7` | 7 / 除水阱温度（℃） | cshtml 标签 |
| `fid_8` | 8 / GC-MS软件 | cshtml 标签 |
| `fid_9` | 1 / 仪器状态 | cshtml 标签 |
| `fsq_1` | 1 / 氢气流量（ 30ml/min ） | cshtml 标签 |
| `fsq_2` | 2 / 零气压力（ 0.4MPa ） | cshtml 标签 |
| `fsq_3` | 3 / 变色硅胶 | cshtml 标签 |
| `fsq_4` | 4 / 活性炭 | cshtml 标签 |
| `mpa_1` | 1 / 氦气（Mpa） | cshtml 标签 |
| `mpa_2` | 2 / 氮气（Mpa） | cshtml 标签 |
| `mpa_3` | 3 / 氢气（Mpa） | cshtml 标签 |
| `mpa_4` | 4 / 零气系统 | cshtml 标签 |
| `mpa_5` | 1 / 氦气（ MPa ） | cshtml 标签 |
| `mpa_6` | 2 / 内标气（MPa） | cshtml 标签 |
| `ms_10` | 2 / 高碳进样量（15ml/min） | cshtml 标签 |
| `ms_11` | 3 / 低碳进样量（15ml/min） | cshtml 标签 |
| `ms_12` | 4 / 冷阱温度（ ≤-140℃ ） | cshtml 标签 |
| `fid_10` | 2 / 高碳进样量（15ml/min） | cshtml 标签 |
| `fid_11` | 3 / 低碳进样量（15ml/min） | cshtml 标签 |
| `fid_12` | 4 / 冷阱温度（ ≤-140℃ ） | cshtml 标签 |
| `zftj_1` | 1 / 温度（ ＜30℃ ） | cshtml 标签 |
| `zftj_2` | 2 / 湿度（ ＜80% ） | cshtml 标签 |
| `zftj_3` | 3 / 大气采样系统 | cshtml 标签 |
| `change_1` | 1 / 内标气 | cshtml 标签 |
| `change_2` | 2 / 外标气 | cshtml 标签 |
| `change_3` | 3 / 二氧化碳祛除管 | cshtml 标签 |
| `change_4` | 4 / 颗粒物过滤膜 | cshtml 标签 |
| `change_5` | 1 / 外标气 | cshtml 标签 |
| `change_6` | 2 / 颗粒物过滤膜 | cshtml 标签 |
| `change_7` | 3 / 变色硅胶 | cshtml 标签 |
| `change_8` | 4 / 纯水 | cshtml 标签 |
| `fsq_remark_1` | 1 / 氢气流量（ 30ml/min ） | cshtml 标签 |
| `fsq_remark_2` | 2 / 零气压力（ 0.4MPa ） | cshtml 标签 |
| `fsq_remark_3` | 3 / 变色硅胶 | cshtml 标签 |
| `fsq_remark_4` | 4 / 活性炭 | cshtml 标签 |
| `mpa_remark_1` | 1 / 氦气（Mpa） | cshtml 标签 |
| `mpa_remark_2` | 2 / 氮气（Mpa） | cshtml 标签 |
| `mpa_remark_3` | 3 / 氢气（Mpa） | cshtml 标签 |
| `mpa_remark_4` | 4 / 零气系统 | cshtml 标签 |
| `mpa_remark_5` | 1 / 氦气（ MPa ） | cshtml 标签 |
| `mpa_remark_6` | 2 / 内标气（MPa） | cshtml 标签 |
| `zftj_remark_1` | 1 / 温度（ ＜30℃ ） | cshtml 标签 |
| `zftj_remark_2` | 2 / 湿度（ ＜80% ） | cshtml 标签 |
| `zftj_remark_3` | 3 / 大气采样系统 | cshtml 标签 |
| `fidms_remark_1` | 1 / 仪器状态 | cshtml 标签 |
| `fidms_remark_2` | 2 / 空气进样量（400ml） | cshtml 标签 |
| `fidms_remark_3` | 3 / 外标进样量（200ml） | cshtml 标签 |
| `fidms_remark_4` | 4 / 内标进样量（90ml） | cshtml 标签 |
| `fidms_remark_5` | 5 / TH-300软件运行情况 | cshtml 标签 |
| `fidms_remark_6` | 6 / 捕集阱温度（小于-150℃） | cshtml 标签 |
| `fidms_remark_7` | 7 / 除水阱温度（℃） | cshtml 标签 |
| `fidms_remark_8` | 8 / GC-MS软件 | cshtml 标签 |
| `fidms_remark_9` | 1 / 仪器状态 | cshtml 标签 |
| `change_remark_1` | 1 / 内标气 | cshtml 标签 |
| `change_remark_2` | 2 / 外标气 | cshtml 标签 |
| `change_remark_3` | 3 / 二氧化碳祛除管 | cshtml 标签 |
| `change_remark_4` | 4 / 颗粒物过滤膜 | cshtml 标签 |
| `change_remark_5` | 1 / 外标气 | cshtml 标签 |
| `change_remark_6` | 2 / 颗粒物过滤膜 | cshtml 标签 |
| `change_remark_7` | 3 / 变色硅胶 | cshtml 标签 |
| `change_remark_8` | 4 / 纯水 | cshtml 标签 |
| `fidms_remark_10` | 2 / 高碳进样量（15ml/min） | cshtml 标签 |
| `fidms_remark_11` | 3 / 低碳进样量（15ml/min） | cshtml 标签 |

**平台校验器：**`fid_7`=required,double；`mpa_1`=required,double；`mpa_2`=required,double；`mpa_3`=required,double；`mpa_4`=required,double；`ms_7`=required,double


## Sup_RF_thybYearMaintain（sup_rf_thybyearmaintain）
- 源码依据：实体 `Sup_RF_thybYearMaintain`、视图 `Sup_RF_thybYearMaintain.cshtml`、Vue 移植版 x2

| 列 | 含义 | 来源 |
| --- | --- | --- |
| `remark_1` | 1 / 采样管清洁 | cshtml 标签 |
| `remark_2` | 2 / 捕集阱散热片清洁 | cshtml 标签 |
| `remark_3` | 3 / 六通阀清洁 | cshtml 标签 |
| `remark_4` | 4 / 十二位阀清洁 | cshtml 标签 |
| `result_1` | 1 / 采样管清洁 | cshtml 标签 |
| `result_2` | 2 / 捕集阱散热片清洁 | cshtml 标签 |
| `result_3` | 3 / 六通阀清洁 | cshtml 标签 |
| `result_4` | 4 / 十二位阀清洁 | cshtml 标签 |


## 三层源码均未覆盖的 tag

- RF_D_GreenHouseCheck　←《组分仪器工单规则》：（温室气体相关）
