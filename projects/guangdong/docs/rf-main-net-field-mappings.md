# 主网 RF 表单 列名→字段含义 权威映射（广东运维平台源码）

- 实体：`SummerFresh.Maintenance/Entity/ReportForms/**`（`[Table]` 表名 + 属性 `<summary>` 注释；ORM 列名=属性名）。
- 视图：`SummerFresh.MVC/Views/ReportForms`、`Views/MtcWorkingOrder`、`Areas/Sup/Views/QcForm` 的 `RF_*.cshtml`（中文标签 ↔ `@Html.TextBoxFor(m => m.列)` 绑定 + `validator` 校验器）。
- 用途：主网 `rf_*` 审计规则（range/required/formula/enum/multipoint/position/unit 等档案）的列语义与必填口径核对；同时纠正 `column-semantics.md`「主网表单题目项字典」误用（`RF_ITEM` 实为工单耗材/附件记录表，见 `opa-source-gap-analysis.md`）。

覆盖：实体表 73 个（带注释 73），视图模型 59 个。

## PW_TASK
- 实体文件：`ReportForms/PW_TASK.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `STATE` |  |  |
| `EDTDATE` |  |  |
| `SDTDATE` |  |  |
| `PWTASKID` | 流水号 |  |
| `RULENAME` |  |  |
| `RULETYPE` |  |  |
| `RULECYCLE` |  |  |
| `STATIONID` |  |  |
| `PLANWORKID` |  |  |
| `PWTASKTIME` |  |  |
| `PWUNITPLANID` | 单位计划ID |  |
| `FINISHPWTASKTIME` |  |  |

## PW_TASKITEM
- 实体文件：`ReportForms/PW_TASKITEM.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `STATE` |  |  |
| `EDTDATE` |  |  |
| `SDTDATE` |  |  |
| `BASEDATE` | 计划项的基准日期 |  |
| `PWTASKID` |  |  |
| `CREATETIME` | 创建时间 |  |
| `TASKUSERID` |  |  |
| `RULEITEMTAG` |  |  |
| `CREATEUSERID` | 创建人 |  |
| `FINISHUSERID` |  |  |
| `PWTASKITEMID` | 流水号 |  |
| `POLLUTANTTYPE` |  |  |
| `FINISHDATETIME` |  |  |
| `FINISHWORKORDERCODE` |  |  |

## PW_TASKITEMTEMP
- 实体文件：`ReportForms/PW_TASKITEM.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `STATE` |  |  |
| `EDTDATE` |  |  |
| `SDTDATE` |  |  |
| `BASEDATE` | 计划项的基准日期 |  |
| `DATATYPE` |  |  |
| `PLANTYPE` |  |  |
| `PWTASKID` |  |  |
| `CREATETIME` | 创建时间 |  |
| `TASKUSERID` |  |  |
| `RULEITEMTAG` |  |  |
| `CREATEUSERID` | 创建人 |  |
| `FINISHUSERID` |  |  |
| `PWTASKITEMID` | 任务项id |  |
| `POLLUTANTTYPE` |  |  |
| `FINISHDATETIME` |  |  |
| `WORKINGORDERCODE` |  |  |
| `FINISHWORKORDERCODE` |  |  |

## PW_TASKTEMP
- 实体文件：`ReportForms/PW_TASK.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `STATE` |  |  |
| `EDTDATE` |  |  |
| `SDTDATE` |  |  |
| `DATATYPE` |  |  |
| `PLANTYPE` |  |  |
| `PWTASKID` | 任务ID |  |
| `RULENAME` |  |  |
| `RULETYPE` |  |  |
| `RULECYCLE` |  |  |
| `STATIONID` |  |  |
| `PLANWORKID` |  |  |
| `PWTASKTIME` |  |  |
| `PWUNITPLANID` | 单位计划ID |  |
| `FINISHPWTASKTIME` |  |  |
| `WORKINGORDERCODE` |  |  |

## RF_BCMonitorInspection
- 实体文件：`ReportForms/RF_BCMonitorInspection.cs`
- 视图：Views/ReportForms/RF_BCMonitorInspection.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `CAP` |  | 防虫雨帽 / 检查/清洁 |
| `OTHER` |  | 其它 |
| `AREAID` |  |  |
| `CUTTER` |  | 切割器 / 检查/清洁 |
| `FILTER` |  | 过滤器 / 按需 |
| `FORMTYPE` |  |  |
| `CAPREMARK` |  | 防虫雨帽 / 检查/清洁 |
| `CHECKDATE` |  |  |
| `PAPERTAPE` |  | 纸带 / 按需 |
| `STATIONID` |  |  |
| `CREATEDATE` |  |  |
| `DEVICECODE` |  | 仪器型号 / 仪器编号 |
| `REVIEWDATE` |  |  |
| `AUDITORDATE` |  |  |
| `DEVICEMODEL` |  | 仪器型号 / 仪器编号 |
| `LEAKAGETEST` |  | 检漏测试 / 检查 |
| `PROCESSTYPE` |  |  |
| `CLEANAIRTEST` |  | 清洁空气测试 / 检查 |
| `CUTTERREMARK` |  | 切割器 / 检查/清洁 |
| `FILTERREMARK` |  | 过滤器 / 按需 |
| `PREPARERDATE` |  |  |
| `REVIEWUSERID` |  |  |
| `AUDITORUSERID` |  |  |
| `DEWATERBOTTLE` |  | 除水汽瓶 / 检查 |
| `OPTICALCAVITY` |  | 光腔 / 检查/清洁 / 半年 |
| `STABILITYTEST` |  | 稳定性测试 / 检查 |
| `TIMEDATEAFTER` |  | 时间日期 / 检查/校准 |
| `PREPARERUSERID` |  |  |
| `RFWBCMONITORID` |  |  |
| `SAMPLELINETUBE` |  | 样气线管 / 检查/清洁 / 每月 |
| `TIMEDATEBEFORE` |  | 时间日期 / 检查/校准 |
| `TIMEDATEREMARK` |  | 时间日期 / 检查/校准 |
| `PAPERTAPEREMARK` |  | 纸带 / 按需 |
| `DATATRANSMISSION` |  | 数据传输 / 检查 / 每周 |
| `OPERATIONSUNITID` |  |  |
| `WORKINGORDERCODE` |  |  |
| `LEAKAGETESTREMARK` |  | 检漏测试 / 检查 |
| `CLEANAIRTESTREMARK` |  | 清洁空气测试 / 检查 |
| `MAINTENANCERESULTS` |  | 维修结果 |
| `PROBLEMDESCRIPTION` |  | 维修记录 / 问题描述 |
| `DEWATERBOTTLEREMARK` |  | 除水汽瓶 / 检查 |
| `OPTICALCAVITYREMARK` |  | 光腔 / 检查/清洁 / 半年 |
| `STABILITYTESTREMARK` |  | 稳定性测试 / 检查 |
| `INSTRUMENTPARAMETERS` |  | 仪器参数 / 检查 |
| `SAMPLELINETUBEREMARK` |  | 样气线管 / 检查/清洁 / 每月 |
| `FLOWVERIFICATIONAFTER` |  | 流量验证 / 检查/清洁 |
| `DATATRANSMISSIONREMARK` |  | 数据传输 / 检查 / 每周 |
| `FLOWVERIFICATIONBEFORE` |  | 流量验证 / 检查/清洁 |
| `FLOWVERIFICATIONREMARK` |  | 流量验证 / 检查/清洁 |
| `INSTRUMENTPARAMETERSREMARK` |  | 仪器参数 / 检查 |
| `OPTICALCAVITYSLIDERLUBRICATION` |  | 光腔滑块润滑 / 保养 / 每年 |
| `OPTICALCAVITYSLIDERLUBRICATIONREMARK` |  | 光腔滑块润滑 / 保养 / 每年 |

**平台校验器：**`DEVICECODE`=required；`DEVICEMODEL`=required

## RF_CUSTOMITEM
- 实体文件：`ReportForms/RF_CUSTOMITEM.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ITEMID` | 耗材Id |  |
| `REMARK` | 备注 |  |
| `RFCIID` | 明细ID |  |
| `CHILDID` | 子项Id |  |
| `IMGPATH` | 凭证路径 |  |
| `ITEMNUM` | 数量 |  |
| `ITEMNAME` | 耗材名称 |  |
| `CHILDNAME` | 子项名称 |  |
| `CREATEDATE` | 创建时间 |  |
| `UPDATEDATE` | 修改时间 |  |
| `RULEITEMTAG` | 报表类型 |  |
| `CREATEUSERID` | 创建用户 |  |
| `UPDATEUSERID` | 修改用户 |  |
| `POLLUTANTTYPE` | 监测类型 |  |
| `WORKINGORDERCODE` | 工单编号 |  |

## RF_HY_EnvironmentHumidity
- 实体文件：`ReportForms/RF_Q_GaseousFlowCheck.cs`
- 视图：Views/ReportForms/RF_HY_EnvironmentHumidity.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `AREAID` | 省市区 |  |
| `REMARK` |  |  |
| `EDTTIME` |  | 操作日期 / 开始时间 / 结束时间 |
| `SDTTIME` |  | 操作日期 / 开始时间 / 结束时间 |
| `HUMIDITY` | 室内湿度 | 室内温度 / 室内湿度 |
| `SENSORNO` | 传感器编号 | 传感器编号 / 上次校准日期 |
| `SERIALNO` | 序列号 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 | 操作日期 / 开始时间 / 结束时间 |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 仪器型号 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `STATIONCODE` |  |  |
| `TEMPERATURE` | 室内温度 | 室内温度 / 室内湿度 |
| `DEVICEMODEL2` |  |  |
| `OUTFACTORYNO` | 出厂编号 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 监测类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `STANDARDREADNUM` |  | 校准前 / 校准后 |
| `CAILBNEXTREADNUM` |  |  |
| `CAILBPREVREADNUM` |  |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `LASTTIMECAILBTIME1` | 环境湿度传感器资料-上次校准日期 | 传感器编号 / 上次校准日期 |
| `LASTTIMECAILBTIME2` | 使用的标准湿度计资料-上次校准日期 |  |

**平台校验器：**`CAILBNEXTREADNUM`=required；`CAILBPREVREADNUM`=required；`DEVICEMODEL`=required；`HUMIDITY`=required；`OUTFACTORYNO`=required；`POLLUTANTTYPE`=required；`SENSORNO`=required；`STANDARDREADNUM`=required；`TEMPERATURE`=required

## RF_HY_GASEOUSCALIDEVICECHECK
- 实体文件：`ReportForms/RF_HY_GASEOUSCALIDEVICECHECK.cs`
- 视图：Views/ReportForms/RF_HY_GASEOUSCALIDEVICECHECK.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `QY` | 气压 | 气压 / 温度 / 湿度 |
| `SD` | 湿度 | 气压 / 温度 / 湿度 |
| `WD` | 温度 | 气压 / 温度 / 湿度 |
| `JUA1` | 截距a1 | 斜率b= / 截距a= / 相关系数r= |
| `JUA2` | 截距a2 |  |
| `XLB1` | 斜率b1 | 斜率b= / 截距a= / 相关系数r= |
| `XLB2` | 斜率b2 |  |
| `AREAID` | 省市区 |  |
| `XGXSR1` | 相关系数r1 | 斜率b= / 截距a= / 相关系数r= |
| `XGXSR2` | 相关系数r2 |  |
| `YQDSROW1` | 第一行仪器读数 | 1 / 1 L/min |
| `YQDSROW2` | 第二行仪器读数 | 2 / 2 L/min |
| `YQDSROW3` | 第三行仪器读数 | 3 / 3 L/min |
| `YQDSROW4` | 第四行仪器读数 | 4 / 4 L/min |
| `YQDSROW5` | 第五行仪器读数 | 5 / 5 L/min |
| `YQDSROW6` | 第六行仪器读数 | 6 / 6 L/min |
| `YQDSROW7` | 第七行仪器读数 | 7 / 7 L/min |
| `YQDSROW8` | 第八行仪器读数 | 8 / 8 L/min |
| `YQDSROW9` | 第九行仪器读数 | 9 / 9 L/min |
| `CHECKDATE` | 检查时间 | 仪器型号/编号 / 检查时间 |
| `JZLLJCODE` | 校准流量计编号 | 校准流量计型号 / 校准流量计编号 |
| `LLJDSROW1` | 第一行流量计读数 | 1 / 1 L/min |
| `LLJDSROW2` | 第二行流量计读数 | 2 / 2 L/min |
| `LLJDSROW3` | 第三行流量计读数 | 3 / 3 L/min |
| `LLJDSROW4` | 第四行流量计读数 | 4 / 4 L/min |
| `LLJDSROW5` | 第五行流量计读数 | 5 / 5 L/min |
| `LLJDSROW6` | 第六行流量计读数 | 6 / 6 L/min |
| `LLJDSROW7` | 第七行流量计读数 | 7 / 7 L/min |
| `LLJDSROW8` | 第八行流量计读数 | 8 / 8 L/min |
| `LLJDSROW9` | 第九行流量计读数 | 9 / 9 L/min |
| `LLJXZROW1` | 第一行流量计修正读数 | 1 / 1 L/min |
| `LLJXZROW2` | 第二行流量计修正读数 | 2 / 2 L/min |
| `LLJXZROW3` | 第三行流量计修正读数 | 3 / 3 L/min |
| `LLJXZROW4` | 第四行流量计修正读数 | 4 / 4 L/min |
| `LLJXZROW5` | 第五行流量计修正读数 | 5 / 5 L/min |
| `LLJXZROW6` | 第六行流量计修正读数 | 6 / 6 L/min |
| `LLJXZROW7` | 第七行流量计修正读数 | 7 / 7 L/min |
| `LLJXZROW8` | 第八行流量计修正读数 | 8 / 8 L/min |
| `LLJXZROW9` | 第九行流量计修正读数 | 9 / 9 L/min |
| `STATIONID` | 站点ID |  |
| `SYJZQROW1` | 第一行输入校准器值 | 1 / 1 L/min |
| `SYJZQROW2` | 第三行输入校准器值 | 2 / 2 L/min |
| `SYJZQROW3` | 第三行输入校准器值 | 3 / 3 L/min |
| `SYJZQROW4` | 第四行输入校准器值 | 4 / 4 L/min |
| `SYJZQROW5` | 第五行输入校准器值 | 5 / 5 L/min |
| `SYJZQROW6` | 第六行输入校准器值 | 6 / 6 L/min |
| `SYJZQROW7` | 第七行输入校准器值 | 7 / 7 L/min |
| `SYJZQROW8` | 第八行输入校准器值 | 8 / 8 L/min |
| `SYJZQROW9` | 第九行输入校准器值 | 9 / 9 L/min |
| `YQDSROW10` | 第十行仪器读数 | 10 / 10 L/min |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 设备型号/编号 | 仪器型号/编号 / 检查时间 |
| `JZLLJMODEL` | 校准流量计型号 | 校准流量计型号 / 校准流量计编号 |
| `LLJDSROW10` | 第十行流量计读数 | 10 / 10 L/min |
| `LLJXZROW10` | 第十行流量计修正读数 | 10 / 10 L/min |
| `LLKZQROW11` | 第一行一列流量控制器 | 1 / 10 ml/min |
| `LLKZQROW12` | 第一行二列流量控制器 | 1 / 10 ml/min |
| `LLKZQROW13` | 第一行三列流量控制器 | 1 / 10 ml/min |
| `LLKZQROW14` | 第一行四列流量控制器 | 1 / 10 ml/min |
| `LLKZQROW21` | 第二行一列流量控制器 | 2 / 20 ml/min |
| `LLKZQROW22` | 第二行二列流量控制器 | 2 / 20 ml/min |
| `LLKZQROW23` | 第二行三列流量控制器 | 2 / 20 ml/min |
| `LLKZQROW24` | 第二行四列流量控制器 | 2 / 20 ml/min |
| `LLKZQROW31` | 第三行一列流量控制器 | 3 / 30 ml/min |
| `LLKZQROW32` | 第三行二列流量控制器 | 3 / 30 ml/min |
| `LLKZQROW33` | 第三行三列流量控制器 | 3 / 30 ml/min |
| `LLKZQROW34` | 第三行四列流量控制器 | 3 / 30 ml/min |
| `LLKZQROW41` | 第四行一列流量控制器 | 4 / 40 ml/min |
| `LLKZQROW42` | 第四行二列流量控制器 | 4 / 40 ml/min |
| `LLKZQROW43` | 第四行三列流量控制器 | 4 / 40 ml/min |
| `LLKZQROW44` | 第四行四列流量控制器 | 4 / 40 ml/min |
| `LLKZQROW51` | 第五行一列流量控制器 | 5 / 50 ml/min |
| `LLKZQROW52` | 第五行二列流量控制器 | 5 / 50 ml/min |
| `LLKZQROW53` | 第五行三列流量控制器 | 5 / 50 ml/min |
| `LLKZQROW54` | 第五行四列流量控制器 | 5 / 50 ml/min |
| `LLKZQROW61` | 第六行一列流量控制器 | 6 / 60 ml/min |
| `LLKZQROW62` | 第六行二列流量控制器 | 6 / 60 ml/min |
| `LLKZQROW63` | 第六行三列流量控制器 | 6 / 60 ml/min |
| `LLKZQROW64` | 第六行四列流量控制器 | 6 / 60 ml/min |
| `LLKZQROW71` | 第七行一列流量控制器 | 7 / 70 ml/min |
| `LLKZQROW72` | 第七行二列流量控制器 | 7 / 70 ml/min |
| `LLKZQROW73` | 第七行三列流量控制器 | 7 / 70 ml/min |
| `LLKZQROW74` | 第七行四列流量控制器 | 7 / 70 ml/min |
| `LLKZQROW81` | 第八行一列流量控制器 | 8 / 80 ml/min |
| `LLKZQROW82` | 第八行二列流量控制器 | 8 / 80 ml/min |
| `LLKZQROW83` | 第八行三列流量控制器 | 8 / 80 ml/min |
| `LLKZQROW84` | 第八行四列流量控制器 | 8 / 80 ml/min |
| `LLKZQROW91` | 第九行一列流量控制器 | 9 / 90 ml/min |
| `LLKZQROW92` | 第九行二列流量控制器 | 9 / 90 ml/min |
| `LLKZQROW93` | 第九行三列流量控制器 | 9 / 90 ml/min |
| `LLKZQROW94` | 第九行四列流量控制器 | 9 / 90 ml/min |
| `REVIEWDATE` | 复核时间 |  |
| `SYJZQROW10` | 第十行输入校准器值 | 10 / 10 L/min |
| `AUDITORDATE` | 审核时间 |  |
| `LLKZQROW101` | 第十行一列流量控制器 | 10 / 100 ml/min |
| `LLKZQROW102` | 第十行二列流量控制器 | 10 / 100 ml/min |
| `LLKZQROW103` | 第十行三列流量控制器 | 10 / 100 ml/min |
| `LLKZQROW104` | 第十行四列流量控制器 | 10 / 100 ml/min |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `RFHYGASEOUSCALIDEVICECHECKID` | 流水号 |  |

## RF_HY_Humidity
- 实体文件：`ReportForms/RF_Q_GaseousFlowCheck.cs`
- 视图：Views/ReportForms/RF_HY_Humidity.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `AREAID` | 省市区 |  |
| `REMARK` |  |  |
| `EDTTIME` |  | 操作日期 / 开始时间 / 结束时间 |
| `SDTTIME` |  | 操作日期 / 开始时间 / 结束时间 |
| `HUMIDITY` | 室内湿度 | 室内温度 / 室内湿度 |
| `SENSORNO` | 传感器编号 | 传感器编号 / 上次校准日期 |
| `SERIALNO` | 序列号 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 | 操作日期 / 开始时间 / 结束时间 |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 仪器型号 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `STATIONCODE` |  |  |
| `TEMPERATURE` | 室内温度 | 室内温度 / 室内湿度 |
| `DEVICEMODEL2` |  |  |
| `OUTFACTORYNO` | 出厂编号 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 监测类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `STANDARDREADNUM` |  | 校准前 / 校准后 |
| `CAILBNEXTREADNUM` |  | 控制限要求：±4%RH |
| `CAILBPREVREADNUM` |  | 控制限要求：±4%RH |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `LASTTIMECAILBTIME1` | 环境湿度传感器资料-上次校准日期 | 传感器编号 / 上次校准日期 |
| `LASTTIMECAILBTIME2` | 使用的标准湿度计资料-上次校准日期 |  |

**平台校验器：**`CAILBNEXTREADNUM`=required；`CAILBPREVREADNUM`=required；`DEVICEMODEL`=required；`HUMIDITY`=required；`OUTFACTORYNO`=required；`POLLUTANTTYPE`=required；`SENSORNO`=required；`STANDARDREADNUM`=required；`TEMPERATURE`=required

## RF_HY_NOXCONVERSIONRATE
- 实体文件：`ReportForms/RF_HY_NOXCONVERSIONRATE.cs`
- 视图：Views/ReportForms/RF_HY_NOXCONVERSIONRATE.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `BJZH` | 平均转化效率 | 平均转化效率 |
| `ZHXL1` | 转化效率第一次 | 转化效率 |
| `ZHXL2` | 转化效率第二次 | 转化效率 |
| `ZHXL3` | 转化效率第三次 | 转化效率 |
| `AREAID` | 省市区 |  |
| `REMARK` | 结果评价 |  |
| `REMROW11` | rem一行第一次 | 开 / [NO]rem |
| `REMROW12` | rem一行第二次 | 开 / [NO]rem |
| `REMROW13` | rem一行第三次 | 开 / [NO]rem |
| `REMROW21` | rem二行第一次 | [NOx]rem |
| `REMROW22` | rem二行第二次 | [NOx]rem |
| `REMROW23` | rem二行第三次 | [NOx]rem |
| `CHECKDATE` | 检查时间 | 设备型号/编号 / 检查时间 |
| `ORIGROW11` | orig一行第一次 | 满量程80% / 关 / [NO]orig |
| `ORIGROW12` | orig一行第二次 | 满量程80% / 关 / [NO]orig |
| `ORIGROW13` | orig一行第三次 | 满量程80% / 关 / [NO]orig |
| `ORIGROW21` | orig二行第一次 | [NOx]orig |
| `ORIGROW22` | orig二行第二次 | [NOx]orig |
| `ORIGROW23` | orig二行第三次 | [NOx]orig |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 设备型号/编号 | 设备型号/编号 / 检查时间 |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `RFHYNOXCONVERSIONRATEID` | 流水号 |  |

## RF_HY_O3VALUEPASS
- 实体文件：`ReportForms/RF_HY_O3VALUEPASS.cs`
- 视图：Views/ReportForms/RF_HY_O3ValuePass.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ISOK` | 汞灯通道偏差异常时处理记录 | 校准结果 (合格/不合格) |
| `AREAID` | 省市区 |  |
| `AVALUE` | 外光光强（外光光强）检查值 | 校准曲线 |
| `BVALUE` | 外光光强（外光光强）异常时处理记录 | 校准曲线 |
| `REMARK` | 备注 | 备注： |
| `RVALUE` | 汞灯通道偏差检查值 | 校准曲线 |
| `DELIVERFC` | 传递标准溯源方程 | 传递标准溯源方程 |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DELIVERDATE` | 传递标准溯源日期 | 臭氧传递标准 型号及编号： / 传递标准溯源日期 |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `DELIVER1VALUE` | 传递用监测仪示值 | 零点 |
| `DELIVER2VALUE` | 传递用监测仪示值 | 满量程的10％ |
| `DELIVER3VALUE` | 传递用监测仪示值 | 满量程的20％ |
| `DELIVER4VALUE` | 传递用监测仪示值 | 满量程的40％ |
| `DELIVER5VALUE` | 传递用监测仪示值 | 满量程的60％ |
| `DELIVER6VALUE` | 传递用监测仪示值 | 满量程的80％ |
| `DENSITY1VALUE` | 传递标准输出浓度 | 零点 |
| `DENSITY2VALUE` | 传递标准输出浓度 | 满量程的10％ |
| `DENSITY3VALUE` | 传递标准输出浓度 | 满量程的20％ |
| `DENSITY4VALUE` | 传递标准输出浓度 | 满量程的40％ |
| `DENSITY5VALUE` | 传递标准输出浓度 | 满量程的60％ |
| `DENSITY6VALUE` | 传递标准输出浓度 | 满量程的80％ |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 传递日期 | 臭氧校准设备 （工作标准） 型号及编号： / 传递日期 |
| `DELIVERTO1VALUE` | 传递用监测仪示值对应的标准值 | 零点 |
| `DELIVERTO2VALUE` | 传递用监测仪示值对应的标准值 | 满量程的10％ |
| `DELIVERTO3VALUE` | 传递用监测仪示值对应的标准值 | 满量程的20％ |
| `DELIVERTO4VALUE` | 传递用监测仪示值对应的标准值 | 满量程的40％ |
| `DELIVERTO5VALUE` | 传递用监测仪示值对应的标准值 | 满量程的60％ |
| `DELIVERTO6VALUE` | 传递用监测仪示值对应的标准值 | 满量程的80％ |
| `RFWINSPECTIONID` | 流水号 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `DELIVERFROM1VALUE` | 传递用监测仪示值 | 零点 |
| `DELIVERFROM2VALUE` | 传递用监测仪示值 | 满量程的10％ |
| `DELIVERFROM3VALUE` | 传递用监测仪示值 | 满量程的20％ |
| `DELIVERFROM4VALUE` | 传递用监测仪示值 | 满量程的40％ |
| `DELIVERFROM5VALUE` | 传递用监测仪示值 | 满量程的60％ |
| `DELIVERFROM6VALUE` | 传递用监测仪示值 | 满量程的80％ |
| `WORKDENSITY1VALUE` | 工作标准输出浓度 | 零点 |
| `WORKDENSITY2VALUE` | 工作标准输出浓度 | 满量程的10％ |
| `WORKDENSITY3VALUE` | 工作标准输出浓度 | 满量程的20％ |
| `WORKDENSITY4VALUE` | 工作标准输出浓度 | 满量程的40％ |
| `WORKDENSITY5VALUE` | 工作标准输出浓度 | 满量程的60％ |
| `WORKDENSITY6VALUE` | 工作标准输出浓度 | 满量程的80％ |
| `DEVICEDELIVERMODEL` | 臭氧传递标准型号及编号： | 臭氧传递标准 型号及编号： / 传递标准溯源日期 |
| `DEVICEDELIVERTOMODEL` | 传递用臭氧监测仪型号及编号 | 传递用臭氧监测仪型号及编号 |
| `DEVICECALIBRATIONMODEL` | 臭氧校准设备 （工作标准） 型号及编号： | 臭氧校准设备 （工作标准） 型号及编号： / 传递日期 |

**平台校验器：**`AVALUE`=required；`DELIVER4VALUE`=required；`DELIVER5VALUE`=required；`DELIVER6VALUE`=required；`DELIVERFC`=required；`DELIVERFROM4VALUE`=required；`DELIVERFROM5VALUE`=required；`DELIVERFROM6VALUE`=required；`DELIVERTO4VALUE`=required；`DELIVERTO5VALUE`=required；`DENSITY1VALUE`=required；`DENSITY5VALUE`=required；`DEVICECALIBRATIONMODEL`=required；`DEVICEDELIVERMODEL`=required；`DEVICEDELIVERTOMODEL`=required；`ISOK`=required；`RVALUE`=required；`WORKDENSITY4VALUE`=required；`WORKDENSITY5VALUE`=required；`WORKDENSITY6VALUE`=required

## RF_HY_STATIONDEVICEMAINTAIN
- 实体文件：`ReportForms/RF_HY_STATIONDEVICEMAINTAIN.cs`
- 视图：Views/ReportForms/RF_HY_StationDeviceMaintain.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CHECK1DATE` | 检查PM2.5、PM10分析仪相对湿度、温度传感器和动态加热装置是否正常工作维护时间 | 1 / 检查PM2.5、PM10分析仪相对湿度、温度传感器和动态加热装置是否正常工作 |
| `CHECK2DATE` | 更换振荡天平法颗粒物分析仪旁路过滤器维护时间 | 2 / 更换振荡天平法颗粒物分析仪旁路过滤器 |
| `CHECK3DATE` | 更换零气源净化剂和氧化剂维护时间 | 3 / 更换零气源净化剂和氧化剂 |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `CHACK1USERID` | 检查PM2.5、PM10分析仪相对湿度、温度传感器和动态加热装置是否正常工作巡检人 |  |
| `CHACK2USERID` | 更换振荡天平法颗粒物分析仪旁路过滤器巡检人 |  |
| `CHACK3USERID` | 更换零气源净化剂和氧化剂巡检人 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `RFHYSTATIONDEVICEMAINTAINID` | 流水号 |  |

## RF_HY_StationMaintainCheck
- 实体文件：`ReportForms/RF_HY_StationMaintainCheck.cs`
- 视图：Views/ReportForms/RF_HY_StationMaintainCheck.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `YEAR` | 真正的年份 | 年份： |
| `MONTH` | 上半年还是下半年 |  |
| `AREAID` |  |  |
| `CODDRK` | 对CO监测仪进行多点校准 备注 | 5 / 对CO监测仪进行多点校准 |
| `CYCDRK` | 进行臭氧量值传递 备注 | 8 / 进行臭氧量值传递 |
| `LQGHRK` | 更换零气源净化剂和氧化剂 备注 | 9 / 更换零气源净化剂和氧化剂 对零气性能进行检查 |
| `O3DDRK` | 对O3监测仪进行多点校准 备注 | 6 / 对O3监测仪进行多点校准 |
| `REMARK` |  |  |
| `NJDJZRK` | 对能见度仪器进行校准 备注 | 11 / 对能见度仪器进行校准 |
| `NOXDDRK` | 对NOX监测仪进行多点校准 备注 | 4 / 对NOX监测仪进行多点校准 |
| `SO2DDRK` | 对SO2监测仪进行多点校准 备注 | 3 / 对SO2监测仪进行多点校准 |
| `CODDGZQK` | 对CO监测仪进行多点校准 工作情况 | 5 / 对CO监测仪进行多点校准 |
| `CODDUSER` | 对CO监测仪进行多点校准 运维人员 |  |
| `CYCDGZQK` | 进行臭氧量值传递 工作情况 | 8 / 进行臭氧量值传递 |
| `CYCDUSER` | 进行臭氧量值传递 运维人员 |  |
| `DTJZLLRK` | 对动态校准仪流量进行20点检查 备注 | 7 / 对动态校准仪流量进行20点检查 |
| `LQGHGZQK` | 更换零气源净化剂和氧化剂 工作情况 | 9 / 更换零气源净化剂和氧化剂 对零气性能进行检查 |
| `LQGHUSER` | 更换零气源净化剂和氧化剂 运维人员 |  |
| `NOXFXYRK` | 对NOX分析仪钼炉 备注 | 10 / 对NOX分析仪钼炉 转化率进行检查 |
| `O3DDGZQK` | 对O3监测仪进行多点校准 工作情况 | 6 / 对O3监测仪进行多点校准 |
| `O3DDUSER` | 对O3监测仪进行多点校准 运维人员 |  |
| `CHECKDATE` |  |  |
| `NJDJZGZQK` | 对能见度仪器进行校准 工作情况 | 11 / 对能见度仪器进行校准 |
| `NJDJZUSER` | 对能见度仪器进行校准 运维人员 |  |
| `NOXDDGZQK` | 对NOX监测仪进行多点校准 工作情况 | 4 / 对NOX监测仪进行多点校准 |
| `NOXDDUSER` | 对NOX监测仪进行多点校准 运维人员 |  |
| `SO2DDGZQK` | 对SO2监测仪进行多点校准 工作情况 | 3 / 对SO2监测仪进行多点校准 |
| `SO2DDUSER` | 对SO2监测仪进行多点校准 运维人员 |  |
| `STATIONID` |  |  |
| `CREATEDATE` |  |  |
| `DTJZLLGZQK` | 对动态校准仪流量进行20点检查 工作情况 | 7 / 对动态校准仪流量进行20点检查 |
| `DTJZLLUSER` | 对动态校准仪流量进行20点检查 运维人员 |  |
| `NOXFXYGZQK` | 对NOX分析仪钼炉 工作情况 | 10 / 对NOX分析仪钼炉 转化率进行检查 |
| `NOXFXYUSER` | 对NOX分析仪钼炉 运维人员 |  |
| `REVIEWDATE` |  |  |
| `AUDITORDATE` |  |  |
| `CHECKPM10RK` | 检查PM10 备注 | 1 / 检查PM10分析仪相对湿度、 温度传感器和动态加热装置是否正常工作 |
| `CHECKPM25RK` | 检查PM2.5 备注 | 2 / 检查PM2.5分析仪相对湿度、 温度传感器和动态加热装置是否正常工作 |
| `PROCESSTYPE` |  |  |
| `PREPARERDATE` |  |  |
| `REVIEWUSERID` |  |  |
| `AUDITORUSERID` |  |  |
| `CHECKPM10GZQK` | 检查PM10 工作情况 | 1 / 检查PM10分析仪相对湿度、 温度传感器和动态加热装置是否正常工作 |
| `CHECKPM10USER` | 检查PM10 运维人员 |  |
| `CHECKPM25GZQK` | 检查PM2.5 工作情况 | 2 / 检查PM2.5分析仪相对湿度、 温度传感器和动态加热装置是否正常工作 |
| `CHECKPM25USER` | 检查PM2.5 运维人员 |  |
| `POLLUTANTTYPE` |  |  |
| `PREPARERUSERID` |  |  |
| `OPERATIONSUNITID` |  |  |
| `WORKINGORDERCODE` |  |  |
| `STATIONMAINTAINCHECKID` |  |  |

**平台校验器：**`CHECKPM10GZQK`=required；`CHECKPM25GZQK`=required；`CODDGZQK`=required；`CYCDGZQK`=required；`DTJZLLGZQK`=required；`LQGHGZQK`=required；`NJDJZGZQK`=required；`NOXDDGZQK`=required；`NOXFXYGZQK`=required；`O3DDGZQK`=required；`SO2DDGZQK`=required

## RF_HY_VISIBILITYCALI
- 实体文件：`ReportForms/RF_HY_VISIBILITYCALI.cs`
- 视图：Views/ReportForms/RF_HY_VisibilityCali.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `NJD` | 能见度值 | 环境条件 |
| `ATMO` | 大气压力 | 环境条件 |
| `DAMP` | 湿度 | 环境条件 |
| `TEMP` | 温度 | 环境条件 |
| `AREAID` | 省市区 |  |
| `DEBQDD` | 不确定度 |  |
| `REMARK` | 备注 | 备注 |
| `DEMODEL` | 校准板型号 |  |
| `DEXISHU` | 消光系数 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号： | 仪器型号 / 仪器编号 / 校准日期 |
| `ISOK1VALUE` | 是否合格 | 零点 / ≤±10% |
| `ISOK2VALUE` | 是否合格 | 标点 |
| `OTHERVALUE` | 其它 | 环境条件 |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 仪器型号 | 仪器型号 / 仪器编号 / 校准日期 |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `JIAOYAN1VALUE` | 校验结果 | 零点 / ≤±10% |
| `JIAOYAN2VALUE` | 校验结果 | 标点 |
| `BIAOZHUN1VALUE` | 标准要求 | 零点 / ≤±10% |
| `BIAOZHUN2VALUE` | 标准要求 | 标点 |
| `JIAOZHUNRESULT` | 校验结论 | 校验结论 |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 | 仪器型号 / 仪器编号 / 校准日期 |
| `RFWINSPECTIONID` | 流水号 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |

**平台校验器：**`ATMO`=required；`BIAOZHUN1VALUE`=required；`BIAOZHUN2VALUE`=required；`DAMP`=required；`DEBQDD`=required；`DEMODEL`=required；`DEVICECODE`=required；`DEVICEMODEL`=required；`DEXISHU`=required；`ISOK1VALUE`=required；`ISOK2VALUE`=required；`JIAOYAN1VALUE`=required；`JIAOYAN2VALUE`=required；`NJD`=required；`OTHERVALUE`=required；`TEMP`=required

## RF_ITEM
- 实体文件：`ReportForms/RF_W_ITEM.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `TYPES` | 类型 |  |
| `ITEMID` | 耗材Id |  |
| `MARKID` | 标志ID用于APP上传更换前后是否同一条 |  |
| `REMARK` | 凭证说明 |  |
| `IMGPATH` | 更换前的凭证路径 |  |
| `ITEMNUM` | 耗材数量 |  |
| `ITEMNAME` | 耗材名称 |  |
| `REGIONID` | 工单的站点所在区域 |  |
| `RFITEMID` | 明细ID |  |
| `STATIONID` |  |  |
| `CREATETIME` | 创建时间 |  |
| `PROCESSTYPE` |  |  |
| `RULEITEMTAG` | 报表类型 |  |
| `IMGPATHAFTER` | 更换后的凭证路径 |  |
| `POLLUTANTTYPE` | 监测类型 |  |
| `OPERATIONSUNITID` | 工单的站点所属运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |

## RF_M_GASEOUSCALICHECK
- 实体文件：`ReportForms/RF_M_GaseousCaliCheck.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `HUMIDITY` | 湿度 |  |
| `PRESSURE` | 气压 |  |
| `CHECKDATE` | 检查日期 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICECODEN` | 仪器编号 |  |
| `DEVICEMODEL` | 仪器型号 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `TEMPERATURE` | 温度 |  |
| `CALIFLOWCODE` | 校准流量计编号 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `CALIFLOWMODEL` | 校准流量计型号 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `FLOWERRORVALUE10L` | 0-10 L/min流量控制器误差 |  |
| `FLOWMETERVALUE10L` | 0-10 L/min流量控制器流量计读数 |  |
| `FLOWDEVICEVALUE10L` | 0-10 L/min流量控制器仪器读数 |  |
| `FLOWERRORVALUE100ML` | 0-100 ml/min流量控制器误差 |  |
| `FLOWMETERVALUE100ML` | 0-100 ml/min流量控制器流量计读数 |  |
| `FLOWQUALITYVALUE10L` | 0-10 L/min流量控制质量流量 |  |
| `FLOWDEVICEVALUE100ML` | 0-100 ml/min流量控制器仪器读数 |  |
| `FLOWQUALITYVALUE100ML` | 0-100 ml/min流量控制质量流量 |  |
| `RFMGASEOUSCALICHECKID` | 流水号 |  |

## RF_M_GASEOUSCALIDEVICECHECK
- 实体文件：`ReportForms/RF_HY_GASEOUSCALIDEVICECHECK.cs`
- 视图：Views/ReportForms/RF_M_GASEOUSCALIDEVICECHECK.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `QY` | 气压 | 气压 / 温度 / 湿度 |
| `SD` | 湿度 | 气压 / 温度 / 湿度 |
| `WD` | 温度 | 气压 / 温度 / 湿度 |
| `JUA1` | 截距a1 | 斜率b= / 截距a= / 相关系数r= |
| `JUA2` | 截距a2 |  |
| `XLB1` | 斜率b1 | 斜率b= / 截距a= / 相关系数r= |
| `XLB2` | 斜率b2 |  |
| `AREAID` | 省市区 |  |
| `XGXSR1` | 相关系数r1 | 斜率b= / 截距a= / 相关系数r= |
| `XGXSR2` | 相关系数r2 |  |
| `YQDSROW1` | 第一行仪器读数 | 1 / 1 L/min |
| `YQDSROW2` | 第二行仪器读数 | 2 / 2 L/min |
| `YQDSROW3` | 第三行仪器读数 | 3 / 3 L/min |
| `YQDSROW4` | 第四行仪器读数 | 4 / 4 L/min |
| `YQDSROW5` | 第五行仪器读数 | 5 / 5 L/min |
| `YQDSROW6` | 第六行仪器读数 | 6 / 6 L/min |
| `YQDSROW7` | 第七行仪器读数 | 7 / 7 L/min |
| `YQDSROW8` | 第八行仪器读数 | 8 / 8 L/min |
| `YQDSROW9` | 第九行仪器读数 | 9 / 9 L/min |
| `CHECKDATE` | 检查时间 | 仪器型号/编号 / 检查时间 |
| `JZLLJCODE` | 校准流量计编号 | 校准流量计型号 / 校准流量计编号 |
| `LLJDSROW1` | 第一行流量计读数 | 1 / 1 L/min |
| `LLJDSROW2` | 第二行流量计读数 | 2 / 2 L/min |
| `LLJDSROW3` | 第三行流量计读数 | 3 / 3 L/min |
| `LLJDSROW4` | 第四行流量计读数 | 4 / 4 L/min |
| `LLJDSROW5` | 第五行流量计读数 | 5 / 5 L/min |
| `LLJDSROW6` | 第六行流量计读数 | 6 / 6 L/min |
| `LLJDSROW7` | 第七行流量计读数 | 7 / 7 L/min |
| `LLJDSROW8` | 第八行流量计读数 | 8 / 8 L/min |
| `LLJDSROW9` | 第九行流量计读数 | 9 / 9 L/min |
| `LLJXZROW1` | 第一行流量计修正读数 | 1 / 1 L/min |
| `LLJXZROW2` | 第二行流量计修正读数 | 2 / 2 L/min |
| `LLJXZROW3` | 第三行流量计修正读数 | 3 / 3 L/min |
| `LLJXZROW4` | 第四行流量计修正读数 | 4 / 4 L/min |
| `LLJXZROW5` | 第五行流量计修正读数 | 5 / 5 L/min |
| `LLJXZROW6` | 第六行流量计修正读数 | 6 / 6 L/min |
| `LLJXZROW7` | 第七行流量计修正读数 | 7 / 7 L/min |
| `LLJXZROW8` | 第八行流量计修正读数 | 8 / 8 L/min |
| `LLJXZROW9` | 第九行流量计修正读数 | 9 / 9 L/min |
| `STATIONID` | 站点ID |  |
| `SYJZQROW1` | 第一行输入校准器值 | 1 / 1 L/min |
| `SYJZQROW2` | 第三行输入校准器值 | 2 / 2 L/min |
| `SYJZQROW3` | 第三行输入校准器值 | 3 / 3 L/min |
| `SYJZQROW4` | 第四行输入校准器值 | 4 / 4 L/min |
| `SYJZQROW5` | 第五行输入校准器值 | 5 / 5 L/min |
| `SYJZQROW6` | 第六行输入校准器值 | 6 / 6 L/min |
| `SYJZQROW7` | 第七行输入校准器值 | 7 / 7 L/min |
| `SYJZQROW8` | 第八行输入校准器值 | 8 / 8 L/min |
| `SYJZQROW9` | 第九行输入校准器值 | 9 / 9 L/min |
| `YQDSROW10` | 第十行仪器读数 | 10 / 10 L/min |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 设备型号/编号 | 仪器型号/编号 / 检查时间 |
| `JZLLJMODEL` | 校准流量计型号 | 校准流量计型号 / 校准流量计编号 |
| `LLJDSROW10` | 第十行流量计读数 | 10 / 10 L/min |
| `LLJXZROW10` | 第十行流量计修正读数 | 10 / 10 L/min |
| `LLKZQROW11` | 第一行一列流量控制器 | 1 / 10 ml/min |
| `LLKZQROW12` | 第一行二列流量控制器 | 1 / 10 ml/min |
| `LLKZQROW13` | 第一行三列流量控制器 | 1 / 10 ml/min |
| `LLKZQROW14` | 第一行四列流量控制器 | 1 / 10 ml/min |
| `LLKZQROW21` | 第二行一列流量控制器 | 2 / 20 ml/min |
| `LLKZQROW22` | 第二行二列流量控制器 | 2 / 20 ml/min |
| `LLKZQROW23` | 第二行三列流量控制器 | 2 / 20 ml/min |
| `LLKZQROW24` | 第二行四列流量控制器 | 2 / 20 ml/min |
| `LLKZQROW31` | 第三行一列流量控制器 | 3 / 30 ml/min |
| `LLKZQROW32` | 第三行二列流量控制器 | 3 / 30 ml/min |
| `LLKZQROW33` | 第三行三列流量控制器 | 3 / 30 ml/min |
| `LLKZQROW34` | 第三行四列流量控制器 | 3 / 30 ml/min |
| `LLKZQROW41` | 第四行一列流量控制器 | 4 / 40 ml/min |
| `LLKZQROW42` | 第四行二列流量控制器 | 4 / 40 ml/min |
| `LLKZQROW43` | 第四行三列流量控制器 | 4 / 40 ml/min |
| `LLKZQROW44` | 第四行四列流量控制器 | 4 / 40 ml/min |
| `LLKZQROW51` | 第五行一列流量控制器 | 5 / 50 ml/min |
| `LLKZQROW52` | 第五行二列流量控制器 | 5 / 50 ml/min |
| `LLKZQROW53` | 第五行三列流量控制器 | 5 / 50 ml/min |
| `LLKZQROW54` | 第五行四列流量控制器 | 5 / 50 ml/min |
| `LLKZQROW61` | 第六行一列流量控制器 | 6 / 60 ml/min |
| `LLKZQROW62` | 第六行二列流量控制器 | 6 / 60 ml/min |
| `LLKZQROW63` | 第六行三列流量控制器 | 6 / 60 ml/min |
| `LLKZQROW64` | 第六行四列流量控制器 | 6 / 60 ml/min |
| `LLKZQROW71` | 第七行一列流量控制器 | 7 / 70 ml/min |
| `LLKZQROW72` | 第七行二列流量控制器 | 7 / 70 ml/min |
| `LLKZQROW73` | 第七行三列流量控制器 | 7 / 70 ml/min |
| `LLKZQROW74` | 第七行四列流量控制器 | 7 / 70 ml/min |
| `LLKZQROW81` | 第八行一列流量控制器 | 8 / 80 ml/min |
| `LLKZQROW82` | 第八行二列流量控制器 | 8 / 80 ml/min |
| `LLKZQROW83` | 第八行三列流量控制器 | 8 / 80 ml/min |
| `LLKZQROW84` | 第八行四列流量控制器 | 8 / 80 ml/min |
| `LLKZQROW91` | 第九行一列流量控制器 | 9 / 90 ml/min |
| `LLKZQROW92` | 第九行二列流量控制器 | 9 / 90 ml/min |
| `LLKZQROW93` | 第九行三列流量控制器 | 9 / 90 ml/min |
| `LLKZQROW94` | 第九行四列流量控制器 | 9 / 90 ml/min |
| `REVIEWDATE` | 复核时间 |  |
| `SYJZQROW10` | 第十行输入校准器值 | 10 / 10 L/min |
| `AUDITORDATE` | 审核时间 |  |
| `LLKZQROW101` | 第十行一列流量控制器 | 10 / 100 ml/min |
| `LLKZQROW102` | 第十行二列流量控制器 | 10 / 100 ml/min |
| `LLKZQROW103` | 第十行三列流量控制器 | 10 / 100 ml/min |
| `LLKZQROW104` | 第十行四列流量控制器 | 10 / 100 ml/min |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `RFHYGASEOUSCALIDEVICECHECKID` | 流水号 |  |

## RF_M_GASEOUSFLOWCHECK
- 实体文件：`ReportForms/RF_M_GaseousFlowCheck.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CHECKDATE2` | 检查日期 |  |
| `CREATEDATE` | 创建日期 |  |
| `FLOWRANGCO` | CO流量范围 |  |
| `FLOWRANGO3` | O3流量范围 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `FLOWRANGNO2` | NO2流量范围 |  |
| `FLOWRANGSO2` | SO2流量范围 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `SITUATIONCO` | CO处理情况 |  |
| `SITUATIONO3` | O3处理情况 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `SITUATIONNO2` | NO2处理情况 |  |
| `SITUATIONSO2` | SO2处理情况 |  |
| `AUDITORUSERID` | 审核人 |  |
| `DEVICEMODELCO` | CO仪器型号 |  |
| `DEVICEMODELO3` | O3仪器型号 |  |
| `DEVICEMODELNO2` | NO2仪器型号 |  |
| `DEVICEMODELSO2` | SO2仪器型号 |  |
| `DISPLAYVALUECO` | CO显示值 |  |
| `DISPLAYVALUEO3` | O3显示值 |  |
| `PREPARERUSERID` | 填表人 |  |
| `DISPLAYVALUENO2` | NO2显示值 |  |
| `DISPLAYVALUESO2` | SO2显示值 |  |
| `MEASUREDERRORCO` | CO测量误差 |  |
| `MEASUREDERRORO3` | O3测量误差 |  |
| `MEASUREDVALUECO` | CO测量值 |  |
| `MEASUREDVALUEO3` | O3测量值 |  |
| `MEASUREDERRORNO2` | NO2测量误差 |  |
| `MEASUREDERRORSO2` | SO2测量误差 |  |
| `MEASUREDVALUENO2` | NO2测量值 |  |
| `MEASUREDVALUESO2` | SO2测量值 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `RFMGASEOUSFLOWCHECKID` | 流水号 |  |

## RF_M_GASEOUSFLOWCHECKDETAIL
- 实体文件：`ReportForms/RF_M_GaseousFlowCheckDetail.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `FLOWRANGE` | 流量范围 |  |
| `DEVICEMODEL` | 仪器型号 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `DISPLAYVALUE` | 显示值 |  |
| `MEASUREDVALUE` | 测量值 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `MEASUREMENTERROR` | 测量误差 |  |
| `TREATMENTSITUATION` | 处理情况 |  |
| `RFMGASEOUSFLOWCHECKID` | 主表流水号 |  |

## RF_M_MANUALCOMPARISON
- 实体文件：`ReportForms/RF_M_MANUALCOMPARISON.cs`
- 视图：Views/ReportForms/RF_M_ManualComparison.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `CYRQ` | 采样日期 | if (Model.STATUS != 2) { switch (item.STATUS) { case 0: ; break; case 1: ; break; default: ; break; } } else { ; } } |
| `CYSD` | 采样时段 |  |
| `CYXM` | 采样项目 |  |
| `LJLL` | 累计流量(标况，m3) |  |
| `LMBH` | 滤膜编号 |  |
| `LMZZ` | 滤膜增重(mg) |  |
| `TQZK` | 天气状况 |  |
| `CYHMZ` | 采样后膜重(mg) |  |
| `CYQMZ` | 采样前膜重(mg) |  |
| `CYRID` | 采样人 |  |
| `CZRID` | 称重人 |  |
| `KLWND` | 颗粒物浓度（μg/m3） |  |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 | 备注 |
| `STATUS` | 状态 0未保存 1 已保存 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `SUBMITDATE` | 提交时间 |  |
| `UPDATETIME` | 最后更新时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `SUBMITUSERID` | 提交人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `MANUALCOMPARISONID` |  |  |

## RF_M_MANUALCOMPARISONDETAIL
- 实体文件：`ReportForms/RF_M_MANUALCOMPARISONDETAIL.cs`
- 视图：Views/ReportForms/RF_M_ManualComparison2.cshtml、Views/ReportForms/RF_M_ManualComparisonDetail.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `CCBH` | 出厂编号 | 采样器型号 / 出厂编号 |
| `CYDD` | 采样地点 |  |
| `CYLL` | 采样流量 | 采样流量(L/min) / 实际流量(L/min) |
| `CYRQ` | 采样日期 | 采样日期(年月日) / 采样地点 |
| `CYSJ` | 采样时间 | 采样时间 / 累计工况体积 / 累计标况体积 |
| `LJLL` | 采样体积(标况，m3) | 颗粒物浓度(μg/m3) / 累计流量(标况，m3) |
| `LMBH` | 滤膜编号 | 滤膜编号 / 颗粒物浓度(μg/m3) |
| `LMZZ` | 滤膜增重(mg) | 滤膜增重(mg) / 称重人 |
| `SJLL` | 实际流量 | 采样流量(L/min) / 实际流量(L/min) |
| `TQQK` | 天气情况 |  |
| `TQZK` | 天气状况 | 相对湿度(%RH) / 天气情况 |
| `XDSD` | 相对湿度 | 相对湿度(%RH) / 天气情况 |
| `XDWC` | 相对误差（%） |  |
| `CYHMZ` | 采样后膜重(mg) | 采样前膜重(mg) / 采样后膜重(mg) |
| `CYQMZ` | 采样前膜重(mg) | 采样前膜重(mg) / 采样后膜重(mg) |
| `CYQXH` | 采样器型号及编号 | 采样器型号 / 出厂编号 |
| `CYRID` | 采样人 |  |
| `CZRID` | 称重人 | 滤膜增重(mg) / 称重人 |
| `JLRID` | 记录人 |  |
| `KLWND` | 颗粒物浓度（μg/m3） | 滤膜编号 / 颗粒物浓度(μg/m3) |
| `AREAID` | 省市区 |  |
| `CYJSSJ` | 采样结束时间 | 采样开始时间 / 采样结束时间 |
| `CYKSSJ` | 采样开始时间 | 采样开始时间 / 采样结束时间 |
| `CYSJJG` | 采样时间间隔 | 采样时间 / 累计工况体积 / 累计标况体积 |
| `LJBKTJ` | 累计标况体积 | 采样时间 / 累计工况体积 / 累计标况体积 |
| `LJGKTJ` | 累计工况体积 | 采样时间 / 累计工况体积 / 累计标况体积 |
| `REMARK` | 备注 | 备注： |
| `SGJCJG` | 手工监测结果（μg/m3） |  |
| `SJHJWD` | 实际环境温度 | 采样器环境温度(℃) / 实际环境温度(℃) |
| `STATUS` | 状态 0未保存 1 已保存 |  |
| `YJQKCL` | 异常情况说明及处置 | 异常情况说明及处置： |
| `ZDJCJG` | 自动监测结果（μg/m3） |  |
| `CYQHJWD` | 采样器环境温度 | 采样器环境温度(℃) / 实际环境温度(℃) |
| `SJHJDQY` | 实际环境大气压 | 采样器环境大气压(kPa) / 实际环境大气压(kPa) |
| `CYQHJDQY` | 采样器环境大气压 | 采样器环境大气压(kPa) / 实际环境大气压(kPa) |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `ZDJCYXHBH` | 自动监测仪器型号及编号 |  |
| `CREATEDATE` | 创建日期 |  |
| `MCDETAILID` |  |  |
| `REVIEWDATE` | 复核时间 |  |
| `SUBMITDATE` | 提交时间 |  |
| `UPDATETIME` | 最后更新时间 |  |
| `AUDITORDATE` | 审核时间 | 采样人： / 审核人： / 审核日期： |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `SUBMITUSERID` | 提交人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 采样项目 | 采样项目 |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |

**平台校验器：**`CCBH`=required；`CYHMZ`=required；`CYLL`=required；`CYQHJDQY`=required；`CYQHJWD`=required；`CYQMZ`=required；`CYQXH`=required；`CYSJJG`=required；`CZRID`=required；`KLWND`=required；`LJBKTJ`=required；`LJGKTJ`=required；`LJLL`=required；`LMBH`=required；`LMZZ`=required；`SJHJDQY`=required；`SJHJWD`=required；`SJLL`=required；`TQZK`=required；`XDSD`=required

## RF_M_MEMBRANEWEIGHING
- 实体文件：`ReportForms/RF_M_MEMBRANEWEIGHING.cs`
- 视图：Views/ReportForms/RF_M_MembraneWeighing.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `BEMAVG` | 采样后两次空白滤膜称量平均值 | 采样后两次空白滤膜称量平均值(单位：mg) |
| `BMBAVG` | 采样后两次滤膜称量平均值 | 采样后两次滤膜称量平均值(单位：mg) |
| `HEMAVG` | 采样前两次空白滤膜称量平均值 | 采样前两次空白滤膜称量平均值(单位：mg)： |
| `HMBAVG` | 采样前两次滤膜称量平均值 | 采样前两次滤膜称量平均值(单位：mg)： |
| `REMARK` | 备注 | 备注： |
| `ADDRESS` | 地点 | 日期 / 地点 |
| `CHECKDATE` | 检查时间 | 日期 / 地点 |
| `RFMMBWHID` |  |  |
| `STATIONID` | 站点ID |  |
| `BFIRSTTEMP` | 采样后滤膜第一次温度 | 温度(单位:℃) |
| `CREATEDATE` | 创建日期 |  |
| `HFIRSTTEMP` | 采样前滤膜第一次温度 | 温度(单位:℃) |
| `MCDETAILID` | 采样记录ID |  |
| `REVIEWDATE` | 复核时间 |  |
| `SUBMITDATE` | 提交时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `BALANCECODE` | 天平编号 | 天平型号 / 天平编号 |
| `BSECONDTEMP` | 采样后滤膜第二次温度 | 温度(单位:℃) |
| `HSECONDTEMP` | 采样前滤膜第二次温度 | 温度(单位:℃) |
| `BALANCEMODEL` | 天平型号 | 天平型号 / 天平编号 |
| `BEMFIRSTTIME` | 采样后空白滤膜第一次称量时间 |  |
| `BMBFIRSTTIME` | 采样后滤膜第一次称量时间 |  |
| `CKCONCLUSION` | 检查结论 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `SUBMITUSERID` | 提交人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `BEMSECONDTIME` | 采样后空白滤膜第二次称量时间 |  |
| `BFIRSTENDDATE` | 采样后滤膜第一次结束日期时间 | 结束日期时间： |
| `BMBSECONDTIME` | 采样后滤膜第二次称量时间 |  |
| `HFIRSTENDDATE` | 采样前滤膜第一次结束日期时间 | 结束日期时间： |
| `BEMBRFIRSTTEMP` | 采样后空白滤膜第一次天平室温度 |  |
| `BMBBRFIRSTTEMP` | 采样后滤膜第一次天平室温度 |  |
| `BSECONDENDDATE` | 采样后滤膜第二次结束日期时间 | 结束日期时间： |
| `HEMBRFIRSTTEMP` | 采样前空白滤膜第一次天平室温度 |  |
| `HMBBRFIRSTTEMP` | 采样前滤膜第一次天平室温度 |  |
| `HSECONDENDDATE` | 采样前滤膜第二次结束日期时间 | 结束日期时间： |
| `PREPARERUSERID` | 填表人 |  |
| `BEMBRSECONDTEMP` | 采样后空白滤膜第二次天平室温度 |  |
| `BEMFIRSTQUALITY` | 采样后空白滤膜第一次质量 |  |
| `BFIRSTSTARTDATE` | 采样后滤膜第一次开始日期时间 | 开始日期时间： |
| `BFIRSTTHUMIDITY` | 采样后滤膜第一次湿度 | 湿度(单位：%RH) |
| `BMBBRSECONDTEMP` | 采样后滤膜第二次天平室温度 |  |
| `BMBFIRSTQUALITY` | 采样后滤膜第一次质量 |  |
| `HEMBRSECONDTEMP` | 采样前空白滤膜第二次天平室温度 |  |
| `HEMFIRSTQUALITY` | 采样前空白滤膜第一次质量 |  |
| `HFIRSTSTARTDATE` | 采样前滤膜第一次开始日期时间 | 开始日期时间： |
| `HFIRSTTHUMIDITY` | 采样前滤膜第一次湿度 | 湿度(单位：%RH) |
| `HMBBRSECONDTEMP` | 采样前滤膜第二次天平室温度 |  |
| `HMBFIRSTQUALITY` | 采样前滤膜第一次质量 |  |
| `BEMSECONDQUALITY` | 采样后空白滤膜第二次质量 |  |
| `BMBSECONDQUALITY` | 采样后滤膜第二次质量 |  |
| `BSECONDSTARTDATE` | 采样后滤膜第二次开始日期时间 | 开始日期时间： |
| `BSECONDTHUMIDITY` | 采样后滤膜第二次湿度 | 湿度(单位：%RH) |
| `HEMSECONDQUALITY` | 采样前空白滤膜第二次质量 |  |
| `HMBSECONDQUALITY` | 采样前滤膜第二次质量 |  |
| `HSECONDSTARTDATE` | 采样前滤膜第二次开始日期时间 | 开始日期时间： |
| `HSECONDTHUMIDITY` | 采样前滤膜第二次湿度 | 湿度(单位：%RH) |
| `MEMBRANEMATERIAL` | 滤膜材质 |  |
| `MEMBRANEQUALITY1` | 标准滤膜原始质量 |  |
| `MEMBRANEQUALITY2` | 标准滤膜本次称量质量 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `EMPTYMEMBRANECODE` | 空白滤膜编号 |  |
| `BEMBRFIRSTHUMIDITY` | 采样后空白滤膜第一次天平室湿度 |  |
| `BMBBRFIRSTHUMIDITY` | 采样后滤膜第一次天平室湿度 |  |
| `HEMBRFIRSTHUMIDITY` | 采样前空白滤膜第一次天平室湿度 |  |
| `HMBBRFIRSTHUMIDITY` | 采样前滤膜第一次天平室湿度 |  |
| `BEMBRSECONDHUMIDITY` | 采样后空白滤膜第二次天平室湿度 |  |
| `BMBBRSECONDHUMIDITY` | 采样后滤膜第二次天平室湿度 |  |
| `HEMBRSECONDHUMIDITY` | 采样前空白滤膜第二次天平室湿度 |  |
| `HMBBRSECONDHUMIDITY` | 采样前滤膜第二次天平室湿度 |  |
| `SAMPLINGMEMBRANECODE` | 采样滤膜编号 |  |
| `STANDARDMEMBRANECODE` | 标准滤膜编号 | 标准滤膜检查 / 检查结论 |

**平台校验器：**`ADDRESS`=required；`BALANCECODE`=required；`BALANCEMODEL`=required；`BEMAVG`=required；`BEMBRFIRSTHUMIDITY`=required；`BEMBRFIRSTTEMP`=required；`BEMBRSECONDHUMIDITY`=required；`BEMBRSECONDTEMP`=required；`BEMFIRSTQUALITY`=required；`BEMSECONDQUALITY`=required；`BFIRSTTEMP`=required；`BFIRSTTHUMIDITY`=required；`BMBAVG`=required；`BMBBRFIRSTHUMIDITY`=required；`BMBBRFIRSTTEMP`=required；`BMBBRSECONDHUMIDITY`=required；`BMBBRSECONDTEMP`=required；`BMBFIRSTQUALITY`=required；`BMBSECONDQUALITY`=required；`BSECONDTEMP`=required；`BSECONDTHUMIDITY`=required；`EMPTYMEMBRANECODE`=required；`HEMAVG`=required；`HEMBRFIRSTHUMIDITY`=required；`HEMBRFIRSTTEMP`=required；`HEMBRSECONDHUMIDITY`=required；`HEMBRSECONDTEMP`=required；`HEMFIRSTQUALITY`=required；`HEMSECONDQUALITY`=required；`HFIRSTTEMP`=required；`HFIRSTTHUMIDITY`=required；`HMBAVG`=required；`HMBBRFIRSTHUMIDITY`=required；`HMBBRFIRSTTEMP`=required；`HMBBRSECONDHUMIDITY`=required；`HMBBRSECONDTEMP`=required；`HMBFIRSTQUALITY`=required；`HMBSECONDQUALITY`=required；`HSECONDTEMP`=required；`HSECONDTHUMIDITY`=required；`MEMBRANEMATERIAL`=required；`MEMBRANEQUALITY1`=required；`MEMBRANEQUALITY2`=required；`SAMPLINGMEMBRANECODE`=required；`STANDARDMEMBRANECODE`=required

## RF_M_PMDeviceMaintain
- 实体文件：`ReportForms/RF_M_PMDeviceMaintain.cs`
- 视图：Views/ReportForms/RF_M_PMDeviceMaintain.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` | 流水号 |  |
| `GHLM` | 更换滤膜 |  |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `ENDTIME` | 结束检查时间 | 巡查月份 / 到 |
| `CHECKDATE` | 检查时间 |  |
| `CLOCKPM10` | 校准或检查PM10分析仪的时钟 | 5 / 校准或检查PM10分析仪的时钟 |
| `CLOCKPM25` | 校准或检查PM2.5分析仪的时钟 | 8 / 校准或检查PM2.5分析仪的时钟 |
| `STARTTIME` | 开始检查时间 | 巡查月份 / 到 |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `PRESSUREPM10` | 校准或检查PM10分析仪的气压 | 4 / 校准或检查PM10分析仪的气压 |
| `PRESSUREPM25` | 校准或检查PM2.5分析仪的气压 | 7 / 校准或检查PM2.5分析仪的气压 |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `FILTERPAPERPM10` | 更换PM10分析仪滤纸带（必要时） | 1 / 更换PM10分析仪滤纸带（必要时） |
| `FILTERPAPERPM25` | 更换PM2.5分析仪滤纸带（必要时） | 2 / 更换PM2.5分析仪滤纸带（必要时） |
| `TEMPERATUREPM10` | 校准或检查PM10分析仪的温度 | 3 / 校准或检查PM10分析仪的温度 |
| `TEMPERATUREPM25` | 校准或检查PM2.5分析仪的温度 | 6 / 校准或检查PM2.5分析仪的温度 |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |

**平台校验器：**`CLOCKPM10`=required；`CLOCKPM25`=required；`FILTERPAPERPM10`=required；`FILTERPAPERPM25`=required；`PRESSUREPM10`=required；`PRESSUREPM25`=required；`TEMPERATUREPM10`=required；`TEMPERATUREPM25`=required

## RF_M_STATIONDEVICEMAINTAIN
- 实体文件：`ReportForms/RF_M_StationDeviceMaintain.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CHECK1DATE` | 每月清洗一次制冷系统过滤网维护时间 |  |
| `CHECK2DATE` | 每月清洁一次颗粒物采样头、清理滤水瓶积水维护时间 |  |
| `CHECK3DATE` | 检查、清洁颗粒物分析仪仪器喷嘴、压环、振荡原件腔室等部件维护时间 |  |
| `CHECK4DATE` | 每月清洁仪器风扇防尘网维护时间 |  |
| `CHECK5DATE` | 颗粒物仪器时钟检查；数据采集仪时钟检查维护时间 |  |
| `CHECK6DATE` | 仪器显示数据和数据采集仪之间的一致性检查维护时间 |  |
| `CHECK7DATE` | 检查设备电机运转功能(针对长光程仪器)维护时间 |  |
| `CHECK8DATE` | 每月清洁望远镜前窗玻璃(针对长光程仪器)维护时间 |  |
| `CHECK9DATE` | 每月调整光路(针对长光程仪器)维护时间 |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `CHECK10DATE` | 每月颗粒物监测仪气路检漏 维护时间 |  |
| `CHECK11DATE` | 每月检查采样管加热装置 维护时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `CHACK1USERID` | 每月清洗一次制冷系统过滤网巡检人 |  |
| `CHACK2USERID` | 每月清洁一次颗粒物采样头、清理滤水瓶积水巡检人 |  |
| `CHACK3USERID` | 检查、清洁颗粒物分析仪仪器喷嘴、压环、振荡原件腔室等部件巡检人 |  |
| `CHACK4USERID` | 每月清洁仪器风扇防尘网巡检人 |  |
| `CHACK5USERID` | 颗粒物仪器时钟检查；数据采集仪时钟检查巡检人 |  |
| `CHACK6USERID` | 仪器显示数据和数据采集仪之间的一致性检查巡检人 |  |
| `CHACK7USERID` | 检查设备电机运转功能(针对长光程仪器)巡检人 |  |
| `CHACK8USERID` | 每月清洁望远镜前窗玻璃(针对长光程仪器)巡检人 |  |
| `CHACK9USERID` | 每月颗粒物监测仪气路检漏 巡检人 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `CHECK10USERID` | 每月调整光路(针对长光程仪器)巡检人 |  |
| `CHECK11USERID` | 每月检查采样管加热装置 巡检人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `RFMSTATIONDEVICEMAINTAINID` | 流水号 |  |

## RF_M_StationMaintainCheck
- 实体文件：`ReportForms/RF_M_StationMaintainCheck.cs`
- 视图：Views/ReportForms/RF_M_StationMaintainCheck.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `COLL` | 检查CO分析仪流量 | 7 / 检查CO分析仪流量 |
| `GHLM` | 更换滤膜 |  |
| `O3LL` | 检查O3分析仪流量 | 8 / 检查O3分析仪流量 |
| `SJBF` | 数据备份 | 10 / 数据备份 |
| `YEAR` | 年 | 年份： / 月份： / 运维人员： |
| `MONTH` | 月 |  |
| `NOXLL` | 检查NOX分析仪流量 | 6 / 检查NOX分析仪流量 |
| `SO2LL` | 检查SO2分析仪流量 | 5 / 检查SO2分析仪流量 |
| `AREAID` |  |  |
| `COLLRK` | 检查CO分析仪流量 | 7 / 检查CO分析仪流量 |
| `O3LLRK` | 检查O3分析仪流量 | 8 / 检查O3分析仪流量 |
| `OPUSER` | 运维人员 |  |
| `PM10DB` | PM10自动监测系统同步比对监测 | 11 / PM10自动监测系统同步比对监测 |
| `PM10LL` | 检查PM10监测仪流量 | 3 / 检查PM10监测仪流量 |
| `PM10QG` | 清洗PM10切割器 | 1 / 清洗PM10切割器 |
| `PM25DB` | PM2.5自动监测系统同步比对监测 | 12 / PM2.5自动监测系统同步比对监测 |
| `PM25LL` | 检查PM2.5监测仪流量 | 4 / 检查PM2.5监测仪流量 |
| `PM25QG` | 清洗PM2.5切割器 | 2 / 清洗PM2.5切割器 |
| `REMARK` |  |  |
| `SJBFRK` | 数据备份 | 10 / 数据备份 |
| `DTJZYLL` | 检查动态校准仪流量 | 9 / 检查动态校准仪流量 |
| `NOXLLRK` | 检查NOX分析仪流量 | 6 / 检查NOX分析仪流量 |
| `SO2LLRK` | 检查SO2分析仪流量 | 5 / 检查SO2分析仪流量 |
| `OPUSERRK` | 运维人员 |  |
| `PM10DBRK` | PM10自动监测系统同步比对监测 | 11 / PM10自动监测系统同步比对监测 |
| `PM10LLRK` | 检查PM10监测仪流量 | 3 / 检查PM10监测仪流量 |
| `PM10QGRK` | 清洗PM10切割器 | 1 / 清洗PM10切割器 |
| `PM25DBRK` | PM2.5自动监测系统同步比对监测 | 12 / PM2.5自动监测系统同步比对监测 |
| `PM25LLRK` | 检查PM2.5监测仪流量 | 4 / 检查PM2.5监测仪流量 |
| `PM25QGRK` | 清洗PM2.5切割器 | 2 / 清洗PM2.5切割器 |
| `CHECKDATE` |  |  |
| `DTJZYLLRK` | 检查动态校准仪流量 | 9 / 检查动态校准仪流量 |
| `STATIONID` |  |  |
| `CREATEDATE` |  |  |
| `REVIEWDATE` |  |  |
| `AUDITORDATE` |  |  |
| `PROCESSTYPE` |  |  |
| `PREPARERDATE` |  |  |
| `REVIEWUSERID` |  |  |
| `AUDITORUSERID` |  |  |
| `POLLUTANTTYPE` |  |  |
| `PREPARERUSERID` |  |  |
| `OPERATIONSUNITID` |  |  |
| `WORKINGORDERCODE` |  |  |
| `STATIONMAINTAINCHECKID` |  |  |

**平台校验器：**`COLL`=required；`DTJZYLL`=required；`NOXLL`=required；`O3LL`=required；`PM10LL`=required；`PM25LL`=required；`SO2LL`=required

## RF_PM1MonitorInspection
- 实体文件：`ReportForms/RF_PM1MonitorInspection.cs`
- 视图：Views/ReportForms/RF_PM1MonitorInspection.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `TIME` |  | 时间 / 是否正常 / 月 |
| `OTHER` |  | 其它 |
| `AREAID` |  |  |
| `FLOWCODE` |  | 流量计 / ±5% |
| `FORMTYPE` |  |  |
| `CHECKDATE` |  |  |
| `FLOWMETER` |  | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 |
| `FLOWMODEL` |  | 流量计 / ±5% |
| `PAPERTAPE` |  | 纸带 / 是否正常 |
| `STATIONID` |  |  |
| `THISVALUE` |  | 校准膜 / 是否合格 |
| `CREATEDATE` |  |  |
| `DEVICECODE` |  | 仪器型号 / 仪器编号 |
| `REVIEWDATE` |  |  |
| `AUDITORDATE` |  |  |
| `DEVICEMODEL` |  | 仪器型号 / 仪器编号 |
| `PROCESSTYPE` |  |  |
| `WETNESSCODE` |  | 湿度计 / ±5% |
| `HEADANDBLOCK` |  | 压头和垫块 / 采样头及切割头 / 是否漏气 |
| `ISAIRLEAKAGE` |  | 压头和垫块 / 采样头及切割头 / 是否漏气 |
| `PREPARERDATE` |  |  |
| `PRESSURECODE` |  | 压力计 / ±1kPa |
| `REVIEWUSERID` |  |  |
| `WETNESSMODEL` |  | 湿度计 / ±5% |
| `AUDITORUSERID` |  |  |
| `MOISTUREMETER` |  | 环境湿度 / 仪器显示值 / 流量计显示值 / 是否校准 |
| `ORIGINALVALUE` |  | 校准膜 / 是否合格 |
| `PRESSUREMETER` |  | 环境压力 / 仪器显示值 / 流量计显示值 / 是否校准 |
| `PRESSUREMODEL` |  | 压力计 / ±1kPa |
| `PREPARERUSERID` |  |  |
| `RFWPM1MONITORID` |  |  |
| `TEMPERATURECODE` |  | 温度计 / ±2℃ |
| `CALIBRATIONPOINT` |  | 校准膜 / 是否合格 |
| `DATATRANSMISSION` |  | 数据传输 / 是否正常 / 周 |
| `EXTERNALCLEANING` |  | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 / 半年 |
| `INTERNALCLEANING` |  | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 / 半年 |
| `MEASUREMENTERROR` |  | 校准膜 / 是否合格 |
| `OPERATIONSUNITID` |  |  |
| `SAMPLINGTUBEROAD` |  | 清洗部件 / 外部清洁 / 内部清洁 / 采样管路 / 半年 |
| `TEMPERATUREMODEL` |  | 温度计 / ±2℃ |
| `THERMOMETERVALUE` |  | 环境温度 / 仪器显示值 / 流量计显示值 / 是否校准 / 季度 |
| `WORKINGORDERCODE` |  |  |
| `FLOWISCALIBRATION` |  | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 |
| `FLOWEXPIRATIONDATE` |  | 流量计 / ±5% |
| `MAINTENANCERESULTS` |  | 维修结果 |
| `PROBLEMDESCRIPTION` |  | 维修记录 / 问题描述 |
| `FLOWINSTRUMENTVALUE` |  | 流量 / 仪器显示值 / 流量计显示值 / 是否校准 |
| `FLOWOUTLOOKISNORMAL` |  | 流量计 / ±5% |
| `INSTRUMENTPARAMETERS` |  | 仪器参数 / 是否正常 |
| `WETNESSISCALIBRATION` |  | 环境湿度 / 仪器显示值 / 流量计显示值 / 是否校准 |
| `PRESSUREISCALIBRATION` |  | 环境压力 / 仪器显示值 / 流量计显示值 / 是否校准 |
| `WETNESSEXPIRATIONDATE` |  | 湿度计 / ±5% |
| `PRESSUREEXPIRATIONDATE` |  | 压力计 / ±1kPa |
| `WETNESSINSTRUMENTVALUE` |  | 环境湿度 / 仪器显示值 / 流量计显示值 / 是否校准 |
| `WETNESSOUTLOOKISNORMAL` |  | 湿度计 / ±5% |
| `PRESSUREINSTRUMENTVALUE` |  | 环境压力 / 仪器显示值 / 流量计显示值 / 是否校准 |
| `PRESSUREOUTLOOKISNORMAL` |  | 压力计 / ±1kPa |
| `TEMPERATUREISCALIBRATION` |  | 环境温度 / 仪器显示值 / 流量计显示值 / 是否校准 / 季度 |
| `CALIBRATIONMEMBRANEISPASS` |  | 校准膜 / 是否合格 |
| `TEMPERATUREEXPIRATIONDATE` |  | 温度计 / ±2℃ |
| `SAMPLINGHEADANDCUTTINGHEAD` |  | 压头和垫块 / 采样头及切割头 / 是否漏气 |
| `TEMPERATUREINSTRUMENTVALUE` |  | 环境温度 / 仪器显示值 / 流量计显示值 / 是否校准 / 季度 |
| `TEMPERATUREOUTLOOKISNORMAL` |  | 温度计 / ±2℃ |

**平台校验器：**`DEVICECODE`=required；`DEVICEMODEL`=required

## RF_Q_GASEOUSMULTIPOINT_CO
- 实体文件：`ReportForms/RF_Q_GASEOUSMULTIPOINT_CO.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `JU` | 截距a |  |
| `XL` | 斜率b |  |
| `PPB` | 使用量程 |  |
| `PPM` | 标气瓶浓度 |  |
| `XGXS` | 相关系数r |  |
| `XZJG` | 校准结果 //（合格/不合格） |  |
| `AREAID` | 省市区 |  |
| `LDCODE` | 零气源编号 |  |
| `JZQCODE` | 校准器编号 |  |
| `LDMODEL` | 零气源型号 |  |
| `MCLBZ10` | 满程量10标准值 |  |
| `MCLBZ20` | 满程量20标准值 |  |
| `MCLBZ40` | 满程量40标准值 |  |
| `MCLBZ60` | 满程量60标准值 |  |
| `MCLBZ80` | 满程量80标准值 |  |
| `MCLXY10` | 满程量10响应值 |  |
| `MCLXY20` | 满程量20响应值 |  |
| `MCLXY40` | 满程量40响应值 |  |
| `MCLXY60` | 满程量60响应值 |  |
| `MCLXY80` | 满程量80响应值 |  |
| `PPMCODE` | 标气瓶编号及有效期 |  |
| `REMARKS` | 备注 |  |
| `JZQMODEL` | 校准器型号 |  |
| `MCLBY101` | 满程量10备用记录1 |  |
| `MCLBY102` | 满程量10备用记录2 |  |
| `MCLBY201` | 满程量20备用记录1 |  |
| `MCLBY202` | 满程量20备用记录2 |  |
| `MCLBY401` | 满程量40备用记录1 |  |
| `MCLBY402` | 满程量40备用记录2 |  |
| `MCLBY601` | 满程量60备用记录1 |  |
| `MCLBY602` | 满程量60备用记录2 |  |
| `MCLBY801` | 满程量80备用记录1 |  |
| `MCLBY802` | 满程量80备用记录2 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 |  |
| `LINGDIANBZ` | 零点标准值 |  |
| `LINGDIANXY` | 零点响应值 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 监测仪器名称 |  |
| `LINGDIANBY1` | 零点备用记录1 |  |
| `LINGDIANBY2` | 零点备用记录2 |  |
| `PPMCODEDATE` | 标气瓶有效期 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `MCLEDTDATE10` | 满程量10结束时间 |  |
| `MCLEDTDATE20` | 满程量20结束时间 |  |
| `MCLEDTDATE40` | 满程量40结束时间 |  |
| `MCLEDTDATE60` | 满程量60结束时间 |  |
| `MCLEDTDATE80` | 满程量80结束时间 |  |
| `MCLSDTDATE10` | 满程量10开始时间 |  |
| `MCLSDTDATE20` | 满程量20开始时间 |  |
| `MCLSDTDATE40` | 满程量40开始时间 |  |
| `MCLSDTDATE60` | 满程量60开始时间 |  |
| `MCLSDTDATE80` | 满程量80开始时间 |  |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 |  |
| `LINGDIANEDTDATE` | 零点结束始时间 |  |
| `LINGDIANSDTDATE` | 零点开始时间 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFQGASEOUSCHECKID` |  |  |

## RF_Q_GASEOUSMULTIPOINT_NO2
- 实体文件：`ReportForms/RF_Q_GASEOUSMULTIPOINT_NO2.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `JU` | 截距a |  |
| `XL` | 斜率b |  |
| `PPB` | 使用量程 |  |
| `PPM` | 标气瓶浓度 |  |
| `XGXS` | 相关系数r |  |
| `XZJG` | 校准结果 //（合格/不合格） |  |
| `AREAID` | 省市区 |  |
| `LDCODE` | 零气源编号 |  |
| `JZQCODE` | 校准器编号 |  |
| `LDMODEL` | 零气源型号 |  |
| `MCLBZ10` | 满程量10标准值 |  |
| `MCLBZ20` | 满程量20标准值 |  |
| `MCLBZ40` | 满程量40标准值 |  |
| `MCLBZ60` | 满程量60标准值 |  |
| `MCLBZ80` | 满程量80标准值 |  |
| `MCLXY10` | 满程量10响应值 |  |
| `MCLXY20` | 满程量20响应值 |  |
| `MCLXY40` | 满程量40响应值 |  |
| `MCLXY60` | 满程量60响应值 |  |
| `MCLXY80` | 满程量80响应值 |  |
| `PPMCODE` | 标气瓶编号及有效期 |  |
| `REMARKS` | 备注 |  |
| `JZQMODEL` | 校准器型号 |  |
| `MCLBY101` | 满程量10备用记录1 |  |
| `MCLBY102` | 满程量10备用记录2 |  |
| `MCLBY201` | 满程量20备用记录1 |  |
| `MCLBY202` | 满程量20备用记录2 |  |
| `MCLBY401` | 满程量40备用记录1 |  |
| `MCLBY402` | 满程量40备用记录2 |  |
| `MCLBY601` | 满程量60备用记录1 |  |
| `MCLBY602` | 满程量60备用记录2 |  |
| `MCLBY801` | 满程量80备用记录1 |  |
| `MCLBY802` | 满程量80备用记录2 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 |  |
| `LINGDIANBZ` | 零点标准值 |  |
| `LINGDIANXY` | 零点响应值 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 监测仪器名称 |  |
| `LINGDIANBY1` | 零点备用记录1 |  |
| `LINGDIANBY2` | 零点备用记录2 |  |
| `PPMCODEDATE` | 标气瓶有效期 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `MCLEDTDATE10` | 满程量10结束时间 |  |
| `MCLEDTDATE20` | 满程量20结束时间 |  |
| `MCLEDTDATE40` | 满程量40结束时间 |  |
| `MCLEDTDATE60` | 满程量60结束时间 |  |
| `MCLEDTDATE80` | 满程量80结束时间 |  |
| `MCLSDTDATE10` | 满程量10开始时间 |  |
| `MCLSDTDATE20` | 满程量20开始时间 |  |
| `MCLSDTDATE40` | 满程量40开始时间 |  |
| `MCLSDTDATE60` | 满程量60开始时间 |  |
| `MCLSDTDATE80` | 满程量80开始时间 |  |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 |  |
| `LINGDIANEDTDATE` | 零点结束始时间 |  |
| `LINGDIANSDTDATE` | 零点开始时间 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFQGASEOUSCHECKID` |  |  |

## RF_Q_GASEOUSMULTIPOINT_O3
- 实体文件：`ReportForms/RF_Q_GASEOUSMULTIPOINT_O3.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `JU` | 截距a |  |
| `XL` | 斜率b |  |
| `PPB` | 使用量程 |  |
| `PPM` | 标气瓶浓度 |  |
| `XGXS` | 相关系数r |  |
| `XZJG` | 校准结果 //（合格/不合格） |  |
| `AREAID` | 省市区 |  |
| `LDCODE` | 零气源编号 |  |
| `JZQCODE` | 校准器编号 |  |
| `LDMODEL` | 零气源型号 |  |
| `MCLBZ10` | 满程量10标准值 |  |
| `MCLBZ20` | 满程量20标准值 |  |
| `MCLBZ40` | 满程量40标准值 |  |
| `MCLBZ60` | 满程量60标准值 |  |
| `MCLBZ80` | 满程量80标准值 |  |
| `MCLXY10` | 满程量10响应值 |  |
| `MCLXY20` | 满程量20响应值 |  |
| `MCLXY40` | 满程量40响应值 |  |
| `MCLXY60` | 满程量60响应值 |  |
| `MCLXY80` | 满程量80响应值 |  |
| `PPMCODE` | 标气瓶编号 |  |
| `REMARKS` | 备注 |  |
| `JZQMODEL` | 校准器型号 |  |
| `MCLBY101` | 满程量10备用记录1 |  |
| `MCLBY102` | 满程量10备用记录2 |  |
| `MCLBY201` | 满程量20备用记录1 |  |
| `MCLBY202` | 满程量20备用记录2 |  |
| `MCLBY401` | 满程量40备用记录1 |  |
| `MCLBY402` | 满程量40备用记录2 |  |
| `MCLBY601` | 满程量60备用记录1 |  |
| `MCLBY602` | 满程量60备用记录2 |  |
| `MCLBY801` | 满程量80备用记录1 |  |
| `MCLBY802` | 满程量80备用记录2 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 |  |
| `LINGDIANBZ` | 零点标准值 |  |
| `LINGDIANXY` | 零点响应值 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 监测仪器名称 |  |
| `LINGDIANBY1` | 零点备用记录1 |  |
| `LINGDIANBY2` | 零点备用记录2 |  |
| `PPMCODEDATE` | 标气瓶有效期 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `MCLEDTDATE10` | 满程量10结束时间 |  |
| `MCLEDTDATE20` | 满程量20结束时间 |  |
| `MCLEDTDATE40` | 满程量40结束时间 |  |
| `MCLEDTDATE60` | 满程量60结束时间 |  |
| `MCLEDTDATE80` | 满程量80结束时间 |  |
| `MCLSDTDATE10` | 满程量10开始时间 |  |
| `MCLSDTDATE20` | 满程量20开始时间 |  |
| `MCLSDTDATE40` | 满程量40开始时间 |  |
| `MCLSDTDATE60` | 满程量60开始时间 |  |
| `MCLSDTDATE80` | 满程量80开始时间 |  |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 |  |
| `LINGDIANEDTDATE` | 零点结束始时间 |  |
| `LINGDIANSDTDATE` | 零点开始时间 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFQGASEOUSCHECKID` |  |  |

## RF_Q_GASEOUSMULTIPOINT_SO2
- 实体文件：`ReportForms/RF_Q_GASEOUSMULTIPOINT_SO2.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `JU` | 截距a |  |
| `XL` | 斜率b |  |
| `PPB` | 使用量程 |  |
| `PPM` | 标气瓶浓度 |  |
| `XGXS` | 相关系数r |  |
| `XZJG` | 校准结果 //（合格/不合格） |  |
| `AREAID` | 省市区 |  |
| `LDCODE` | 零气源编号 |  |
| `JZQCODE` | 校准器编号 |  |
| `LDMODEL` | 零气源型号 |  |
| `MCLBZ10` | 满程量10标准值 |  |
| `MCLBZ20` | 满程量20标准值 |  |
| `MCLBZ40` | 满程量40标准值 |  |
| `MCLBZ60` | 满程量60标准值 |  |
| `MCLBZ80` | 满程量80标准值 |  |
| `MCLXY10` | 满程量10响应值 |  |
| `MCLXY20` | 满程量20响应值 |  |
| `MCLXY40` | 满程量40响应值 |  |
| `MCLXY60` | 满程量60响应值 |  |
| `MCLXY80` | 满程量80响应值 |  |
| `PPMCODE` | 标气瓶编号 |  |
| `REMARKS` | 备注 |  |
| `JZQMODEL` | 校准器型号 |  |
| `MCLBY101` | 满程量10备用记录1 |  |
| `MCLBY102` | 满程量10备用记录2 |  |
| `MCLBY201` | 满程量20备用记录1 |  |
| `MCLBY202` | 满程量20备用记录2 |  |
| `MCLBY401` | 满程量40备用记录1 |  |
| `MCLBY402` | 满程量40备用记录2 |  |
| `MCLBY601` | 满程量60备用记录1 |  |
| `MCLBY602` | 满程量60备用记录2 |  |
| `MCLBY801` | 满程量80备用记录1 |  |
| `MCLBY802` | 满程量80备用记录2 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 |  |
| `LINGDIANBZ` | 零点标准值 |  |
| `LINGDIANXY` | 零点响应值 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 监测仪器名称 |  |
| `LINGDIANBY1` | 零点备用记录1 |  |
| `LINGDIANBY2` | 零点备用记录2 |  |
| `PPMCODEDATE` | 标气瓶有效期 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `MCLEDTDATE10` | 满程量10结束时间 |  |
| `MCLEDTDATE20` | 满程量20结束时间 |  |
| `MCLEDTDATE40` | 满程量40结束时间 |  |
| `MCLEDTDATE60` | 满程量60结束时间 |  |
| `MCLEDTDATE80` | 满程量80结束时间 |  |
| `MCLSDTDATE10` | 满程量10开始时间 |  |
| `MCLSDTDATE20` | 满程量20开始时间 |  |
| `MCLSDTDATE40` | 满程量40开始时间 |  |
| `MCLSDTDATE60` | 满程量60开始时间 |  |
| `MCLSDTDATE80` | 满程量80开始时间 |  |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 |  |
| `LINGDIANEDTDATE` | 零点结束始时间 |  |
| `LINGDIANSDTDATE` | 零点开始时间 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFQGASEOUSCHECKID` |  |  |

## RF_Q_GASEOUSPRECISION_CO
- 实体文件：`ReportForms/RF_Q_GASEOUSPRECISION_CO.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `PPB` | 使用量程（PPB） |  |
| `PPM` | 标气瓶浓度 |  |
| `BZPC` | 标准偏差 |  |
| `SHJG` | 审核结果 |  |
| `SSPJS` | 算术平均数 |  |
| `YQSZ1` | 仪器示值1 |  |
| `YQSZ2` | 仪器示值2 |  |
| `YQSZ3` | 仪器示值3 |  |
| `YQSZ4` | 仪器示值4 |  |
| `YQSZ5` | 仪器示值5 |  |
| `YQSZ6` | 仪器示值6 |  |
| `AREAID` | 省市区 |  |
| `LDCODE` | 零气源编号 |  |
| `XDBZPC` | 相对标准偏差 |  |
| `JZQCODE` | 校准器编号 |  |
| `LDMODEL` | 零气源型号 |  |
| `MCLBZ20` | 满程量20标准值 |  |
| `PPMCODE` | 标气瓶来源及编号 |  |
| `REMARKS` | 备注 |  |
| `YQSZ1BZ` | 第一次仪器示值标准值 |  |
| `YQSZ1XY` | 第一次仪器示值响应值 |  |
| `YQSZ2BZ` | 第二次仪器示值标准值 |  |
| `YQSZ2XY` | 第二次仪器示值响应值 |  |
| `YQSZ3BZ` | 第三次仪器示值标准值 |  |
| `YQSZ3XY` | 第三次仪器示值响应值 |  |
| `YQSZ4BZ` | 第四次仪器示值标准值 |  |
| `YQSZ4XY` | 第四次仪器示值响应值 |  |
| `YQSZ5BZ` | 第五次仪器示值标准值 |  |
| `YQSZ5XY` | 第五次仪器示值响应值 |  |
| `YQSZ6BZ` | 第六次仪器示值标准值 |  |
| `YQSZ6XY` | 第六次仪器示值响应值 |  |
| `JZQMODEL` | 校准器型号 |  |
| `YQSZ1BY1` | 第一次仪器示值备用记录1 |  |
| `YQSZ1BY2` | 第一次仪器示值备用记录2 |  |
| `YQSZ2BY1` | 第二次仪器示值备用记录1 |  |
| `YQSZ2BY2` | 第二次仪器示值备用记录2 |  |
| `YQSZ3BY1` | 第三次仪器示值备用记录1 |  |
| `YQSZ3BY2` | 第三次仪器示值备用记录2 |  |
| `YQSZ4BY1` | 第四次仪器示值备用记录1 |  |
| `YQSZ4BY2` | 第四次仪器示值备用记录2 |  |
| `YQSZ5BY1` | 第五次仪器示值备用记录1 |  |
| `YQSZ5BY2` | 第五次仪器示值备用记录2 |  |
| `YQSZ6BY1` | 第六次仪器示值备用记录1 |  |
| `YQSZ6BY2` | 第六次仪器示值备用记录2 |  |
| `AUDITDATE` | 审核日期 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器名称及编号 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 仪器型号 |  |
| `PPMCODEDATE` | 标气瓶有效期 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `YQSZ1EDTDATE` | 第一次仪器示值结束时间 |  |
| `YQSZ1SDTDATE` | 第一次仪器示值开始时间 |  |
| `YQSZ2EDTDATE` | 第二次仪器示值结束时间 |  |
| `YQSZ2SDTDATE` | 第二次仪器示值开始时间 |  |
| `YQSZ3EDTDATE` | 第三次仪器示值结束时间 |  |
| `YQSZ3SDTDATE` | 第三次仪器示值开始时间 |  |
| `YQSZ4EDTDATE` | 第四次仪器示值结束时间 |  |
| `YQSZ4SDTDATE` | 第四次仪器示值开始时间 |  |
| `YQSZ5EDTDATE` | 第五次仪器示值结束时间 |  |
| `YQSZ5SDTDATE` | 第五次仪器示值开始时间 |  |
| `YQSZ6EDTDATE` | 第六次仪器示值结束时间 |  |
| `YQSZ6SDTDATE` | 第六次仪器示值开始时间 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFQGASEOUSPRECISIONID` |  |  |

## RF_Q_GASEOUSPRECISION_NO2
- 实体文件：`ReportForms/RF_Q_GASEOUSPRECISION_NO2.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `PPB` | 使用量程（PPB） |  |
| `PPM` | 标气瓶浓度 |  |
| `BZPC` | 标准偏差 |  |
| `SHJG` | 审核结果 |  |
| `SSPJS` | 算术平均数 |  |
| `YQSZ1` | 仪器示值1 |  |
| `YQSZ2` | 仪器示值2 |  |
| `YQSZ3` | 仪器示值3 |  |
| `YQSZ4` | 仪器示值4 |  |
| `YQSZ5` | 仪器示值5 |  |
| `YQSZ6` | 仪器示值6 |  |
| `AREAID` | 省市区 |  |
| `LDCODE` | 零气源编号 |  |
| `XDBZPC` | 相对标准偏差 |  |
| `JZQCODE` | 校准器编号 |  |
| `LDMODEL` | 零气源型号 |  |
| `MCLBZ20` | 满程量20标准值 |  |
| `PPMCODE` | 标气瓶来源及编号 |  |
| `REMARKS` | 备注 |  |
| `YQSZ1BZ` | 第一次仪器示值标准值 |  |
| `YQSZ1XY` | 第一次仪器示值响应值 |  |
| `YQSZ2BZ` | 第二次仪器示值标准值 |  |
| `YQSZ2XY` | 第二次仪器示值响应值 |  |
| `YQSZ3BZ` | 第三次仪器示值标准值 |  |
| `YQSZ3XY` | 第三次仪器示值响应值 |  |
| `YQSZ4BZ` | 第四次仪器示值标准值 |  |
| `YQSZ4XY` | 第四次仪器示值响应值 |  |
| `YQSZ5BZ` | 第五次仪器示值标准值 |  |
| `YQSZ5XY` | 第五次仪器示值响应值 |  |
| `YQSZ6BZ` | 第六次仪器示值标准值 |  |
| `YQSZ6XY` | 第六次仪器示值响应值 |  |
| `JZQMODEL` | 校准器型号 |  |
| `YQSZ1BY1` | 第一次仪器示值备用记录1 |  |
| `YQSZ1BY2` | 第一次仪器示值备用记录2 |  |
| `YQSZ2BY1` | 第二次仪器示值备用记录1 |  |
| `YQSZ2BY2` | 第二次仪器示值备用记录2 |  |
| `YQSZ3BY1` | 第三次仪器示值备用记录1 |  |
| `YQSZ3BY2` | 第三次仪器示值备用记录2 |  |
| `YQSZ4BY1` | 第四次仪器示值备用记录1 |  |
| `YQSZ4BY2` | 第四次仪器示值备用记录2 |  |
| `YQSZ5BY1` | 第五次仪器示值备用记录1 |  |
| `YQSZ5BY2` | 第五次仪器示值备用记录2 |  |
| `YQSZ6BY1` | 第六次仪器示值备用记录1 |  |
| `YQSZ6BY2` | 第六次仪器示值备用记录2 |  |
| `AUDITDATE` | 审核日期 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器名称及编号 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 仪器型号 |  |
| `PPMCODEDATE` | 标气瓶有效期 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `YQSZ1EDTDATE` | 第一次仪器示值结束时间 |  |
| `YQSZ1SDTDATE` | 第一次仪器示值开始时间 |  |
| `YQSZ2EDTDATE` | 第二次仪器示值结束时间 |  |
| `YQSZ2SDTDATE` | 第二次仪器示值开始时间 |  |
| `YQSZ3EDTDATE` | 第三次仪器示值结束时间 |  |
| `YQSZ3SDTDATE` | 第三次仪器示值开始时间 |  |
| `YQSZ4EDTDATE` | 第四次仪器示值结束时间 |  |
| `YQSZ4SDTDATE` | 第四次仪器示值开始时间 |  |
| `YQSZ5EDTDATE` | 第五次仪器示值结束时间 |  |
| `YQSZ5SDTDATE` | 第五次仪器示值开始时间 |  |
| `YQSZ6EDTDATE` | 第六次仪器示值结束时间 |  |
| `YQSZ6SDTDATE` | 第六次仪器示值开始时间 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFQGASEOUSPRECISIONID` |  |  |

## RF_Q_GASEOUSPRECISION_O3
- 实体文件：`ReportForms/RF_Q_GASEOUSPRECISION_O3.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `PPB` | 使用量程（PPB） |  |
| `PPM` | 标气瓶浓度 |  |
| `BZPC` | 标准偏差 |  |
| `SHJG` | 审核结果 |  |
| `SSPJS` | 算术平均数 |  |
| `YQSZ1` | 仪器示值1 |  |
| `YQSZ2` | 仪器示值2 |  |
| `YQSZ3` | 仪器示值3 |  |
| `YQSZ4` | 仪器示值4 |  |
| `YQSZ5` | 仪器示值5 |  |
| `YQSZ6` | 仪器示值6 |  |
| `AREAID` | 省市区 |  |
| `LDCODE` | 零气源编号 |  |
| `XDBZPC` | 相对标准偏差 |  |
| `JZQCODE` | 校准器编号 |  |
| `LDMODEL` | 零气源型号 |  |
| `MCLBZ20` | 满程量20标准值 |  |
| `PPMCODE` | 标气瓶来源及编号 |  |
| `REMARKS` | 备注 |  |
| `YQSZ1BZ` | 第一次仪器示值标准值 |  |
| `YQSZ1XY` | 第一次仪器示值响应值 |  |
| `YQSZ2BZ` | 第二次仪器示值标准值 |  |
| `YQSZ2XY` | 第二次仪器示值响应值 |  |
| `YQSZ3BZ` | 第三次仪器示值标准值 |  |
| `YQSZ3XY` | 第三次仪器示值响应值 |  |
| `YQSZ4BZ` | 第四次仪器示值标准值 |  |
| `YQSZ4XY` | 第四次仪器示值响应值 |  |
| `YQSZ5BZ` | 第五次仪器示值标准值 |  |
| `YQSZ5XY` | 第五次仪器示值响应值 |  |
| `YQSZ6BZ` | 第六次仪器示值标准值 |  |
| `YQSZ6XY` | 第六次仪器示值响应值 |  |
| `JZQMODEL` | 校准器型号 |  |
| `YQSZ1BY1` | 第一次仪器示值备用记录1 |  |
| `YQSZ1BY2` | 第一次仪器示值备用记录2 |  |
| `YQSZ2BY1` | 第二次仪器示值备用记录1 |  |
| `YQSZ2BY2` | 第二次仪器示值备用记录2 |  |
| `YQSZ3BY1` | 第三次仪器示值备用记录1 |  |
| `YQSZ3BY2` | 第三次仪器示值备用记录2 |  |
| `YQSZ4BY1` | 第四次仪器示值备用记录1 |  |
| `YQSZ4BY2` | 第四次仪器示值备用记录2 |  |
| `YQSZ5BY1` | 第五次仪器示值备用记录1 |  |
| `YQSZ5BY2` | 第五次仪器示值备用记录2 |  |
| `YQSZ6BY1` | 第六次仪器示值备用记录1 |  |
| `YQSZ6BY2` | 第六次仪器示值备用记录2 |  |
| `AUDITDATE` | 审核日期 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器名称及编号 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 仪器型号 |  |
| `PPMCODEDATE` | 标气瓶有效期 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `YQSZ1EDTDATE` | 第一次仪器示值结束时间 |  |
| `YQSZ1SDTDATE` | 第一次仪器示值开始时间 |  |
| `YQSZ2EDTDATE` | 第二次仪器示值结束时间 |  |
| `YQSZ2SDTDATE` | 第二次仪器示值开始时间 |  |
| `YQSZ3EDTDATE` | 第三次仪器示值结束时间 |  |
| `YQSZ3SDTDATE` | 第三次仪器示值开始时间 |  |
| `YQSZ4EDTDATE` | 第四次仪器示值结束时间 |  |
| `YQSZ4SDTDATE` | 第四次仪器示值开始时间 |  |
| `YQSZ5EDTDATE` | 第五次仪器示值结束时间 |  |
| `YQSZ5SDTDATE` | 第五次仪器示值开始时间 |  |
| `YQSZ6EDTDATE` | 第六次仪器示值结束时间 |  |
| `YQSZ6SDTDATE` | 第六次仪器示值开始时间 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFQGASEOUSPRECISIONID` |  |  |

## RF_Q_GASEOUSPRECISION_SO2
- 实体文件：`ReportForms/RF_Q_GASEOUSPRECISION_SO2.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `PPB` | 使用量程（PPB） |  |
| `PPM` | 标气瓶浓度 |  |
| `BZPC` | 标准偏差 |  |
| `SHJG` | 审核结果 |  |
| `SSPJS` | 算术平均数 |  |
| `YQSZ1` | 仪器示值1 |  |
| `YQSZ2` | 仪器示值2 |  |
| `YQSZ3` | 仪器示值3 |  |
| `YQSZ4` | 仪器示值4 |  |
| `YQSZ5` | 仪器示值5 |  |
| `YQSZ6` | 仪器示值6 |  |
| `AREAID` | 省市区 |  |
| `LDCODE` | 零气源编号 |  |
| `XDBZPC` | 相对标准偏差 |  |
| `JZQCODE` | 校准器编号 |  |
| `LDMODEL` | 零气源型号 |  |
| `MCLBZ20` | 满程量20标准值 |  |
| `PPMCODE` | 标气瓶来源及编号 |  |
| `REMARKS` | 备注 |  |
| `YQSZ1BZ` | 第一次仪器示值标准值 |  |
| `YQSZ1XY` | 第一次仪器示值响应值 |  |
| `YQSZ2BZ` | 第二次仪器示值标准值 |  |
| `YQSZ2XY` | 第二次仪器示值响应值 |  |
| `YQSZ3BZ` | 第三次仪器示值标准值 |  |
| `YQSZ3XY` | 第三次仪器示值响应值 |  |
| `YQSZ4BZ` | 第四次仪器示值标准值 |  |
| `YQSZ4XY` | 第四次仪器示值响应值 |  |
| `YQSZ5BZ` | 第五次仪器示值标准值 |  |
| `YQSZ5XY` | 第五次仪器示值响应值 |  |
| `YQSZ6BZ` | 第六次仪器示值标准值 |  |
| `YQSZ6XY` | 第六次仪器示值响应值 |  |
| `JZQMODEL` | 校准器型号 |  |
| `YQSZ1BY1` | 第一次仪器示值备用记录1 |  |
| `YQSZ1BY2` | 第一次仪器示值备用记录2 |  |
| `YQSZ2BY1` | 第二次仪器示值备用记录1 |  |
| `YQSZ2BY2` | 第二次仪器示值备用记录2 |  |
| `YQSZ3BY1` | 第三次仪器示值备用记录1 |  |
| `YQSZ3BY2` | 第三次仪器示值备用记录2 |  |
| `YQSZ4BY1` | 第四次仪器示值备用记录1 |  |
| `YQSZ4BY2` | 第四次仪器示值备用记录2 |  |
| `YQSZ5BY1` | 第五次仪器示值备用记录1 |  |
| `YQSZ5BY2` | 第五次仪器示值备用记录2 |  |
| `YQSZ6BY1` | 第六次仪器示值备用记录1 |  |
| `YQSZ6BY2` | 第六次仪器示值备用记录2 |  |
| `AUDITDATE` | 审核日期 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器名称及编号 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 仪器型号 |  |
| `PPMCODEDATE` | 标气瓶有效期 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `YQSZ1EDTDATE` | 第一次仪器示值结束时间 |  |
| `YQSZ1SDTDATE` | 第一次仪器示值开始时间 |  |
| `YQSZ2EDTDATE` | 第二次仪器示值结束时间 |  |
| `YQSZ2SDTDATE` | 第二次仪器示值开始时间 |  |
| `YQSZ3EDTDATE` | 第三次仪器示值结束时间 |  |
| `YQSZ3SDTDATE` | 第三次仪器示值开始时间 |  |
| `YQSZ4EDTDATE` | 第四次仪器示值结束时间 |  |
| `YQSZ4SDTDATE` | 第四次仪器示值开始时间 |  |
| `YQSZ5EDTDATE` | 第五次仪器示值结束时间 |  |
| `YQSZ5SDTDATE` | 第五次仪器示值开始时间 |  |
| `YQSZ6EDTDATE` | 第六次仪器示值结束时间 |  |
| `YQSZ6SDTDATE` | 第六次仪器示值开始时间 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFQGASEOUSPRECISIONID` |  |  |

## RF_Q_GaseousFlowCheck
- 实体文件：`ReportForms/RF_Q_GaseousFlowCheck.cs`
- 视图：Views/ReportForms/RF_Q_GaseousFlowCheck.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `P_AS` |  | 出厂编号 / 斜率 |
| `P_BS` |  | 上次校准日期 / 截距 / 测量显示值 |
| `P_PA` |  | 下次校准日期 / 截距 / 真实值(Pa) |
| `P_RS` |  | 下次校准日期 / 截距 / 真实值(Pa) |
| `T_TA` |  | 上次校准日期 / 下次校准日期 / 真实值(Ta) |
| `D_AC1` |  | 流量检查日期 / 上一次 / 零气 |
| `D_AC2` |  | 下一次 / 标准气 |
| `D_BC1` |  | 流量检查日期 / 上一次 / 零气 |
| `D_BC2` |  | 下一次 / 标准气 |
| `D_RC1` |  | 流量检查日期 / 上一次 / 零气 |
| `D_RC2` |  | 下一次 / 标准气 |
| `F_AS1` |  | 零气 |
| `F_AS2` |  | 标准气 |
| `F_BS1` |  | 零气 |
| `F_BS2` |  | 标准气 |
| `F_RS1` |  | 零气 |
| `F_RS2` |  | 标准气 |
| `AREAID` |  |  |
| `REMARK` |  | 备注 |
| `EDTTIME` |  | 操作日期 / 开始时间 / 结束时间 |
| `RF_D_20` |  | 20% |
| `RF_D_35` |  | 35% |
| `RF_D_50` |  | 50% |
| `RF_D_60` |  | 60% |
| `RF_D_80` |  | 标准气 / 80% |
| `RF_D_85` |  | 零气 / 85% |
| `SDTTIME` |  | 操作日期 / 开始时间 / 结束时间 |
| `DF_QM_20` |  | 20% |
| `DF_QM_35` |  | 35% |
| `DF_QM_50` |  | 50% |
| `DF_QM_60` |  | 60% |
| `DF_QM_80` |  | 标准气 / 80% |
| `DF_QM_85` |  | 零气 / 85% |
| `HUMIDITY` |  | 校准人员 / 室内温度 / 室内湿度 |
| `RF_QA_20` |  | 20% |
| `RF_QA_35` |  | 35% |
| `RF_QA_50` |  | 50% |
| `RF_QA_60` |  | 60% |
| `RF_QA_80` |  | 标准气 / 80% |
| `RF_QA_85` |  | 零气 / 85% |
| `RF_QS_20` |  | 20% |
| `RF_QS_35` |  | 35% |
| `RF_QS_50` |  | 50% |
| `RF_QS_60` |  | 60% |
| `RF_QS_80` |  | 标准气 / 80% |
| `RF_QS_85` |  | 零气 / 85% |
| `CHECKDATE` |  |  |
| `STATIONID` |  |  |
| `CREATEDATE` |  | 操作日期 / 开始时间 / 结束时间 |
| `REVIEWDATE` |  |  |
| `AUDITORDATE` |  |  |
| `PROCESSTYPE` |  |  |
| `TEMPERATURE` |  | 校准人员 / 室内温度 / 室内湿度 |
| `DF_VALUVE_20` |  | 20% |
| `DF_VALUVE_35` |  | 35% |
| `DF_VALUVE_50` |  | 50% |
| `DF_VALUVE_60` |  | 60% |
| `DF_VALUVE_80` |  | 标准气 / 80% |
| `DF_VALUVE_85` |  | 零气 / 85% |
| `PREPARERDATE` |  |  |
| `REVIEWUSERID` |  |  |
| `RF_VALUVE_20` |  | 20% |
| `RF_VALUVE_35` |  | 35% |
| `RF_VALUVE_50` |  | 50% |
| `RF_VALUVE_60` |  | 60% |
| `RF_VALUVE_80` |  | 标准气 / 80% |
| `RF_VALUVE_85` |  | 零气 / 85% |
| `AUDITORUSERID` |  |  |
| `D_DEVICEMODEL` |  | 仪器型号 / 流量校准方程(Y_真实值，X_显示值) |
| `D_FACTORYCODE` |  | 出厂编号 / 斜率(Ac) / 截距(Bc) / 相关系数(Rc) |
| `POLLUTANTTYPE` |  |  |
| `P_DEVICEMODEL` |  | 设备型号 / 校准方程(Y_真实值，X_显示值) |
| `P_FACTORYCODE` |  | 出厂编号 / 斜率 |
| `T_DEVICEMODEL` |  | 设备型号 / 出厂编号 |
| `T_FACTORYCODE` |  | 设备型号 / 出厂编号 |
| `F_DEVICEMODEL1` |  | 零气 |
| `F_DEVICEMODEL2` |  | 标准气 |
| `F_FACTORYCODE1` |  | 零气 |
| `F_FACTORYCODE2` |  | 标准气 |
| `PREPARERUSERID` |  |  |
| `CALIBRATEUSERID` |  |  |
| `OPERATIONSUNITID` |  |  |
| `P_MEASURINGRANGE` |  |  |
| `P_MEASURINGVALUE` |  | 上次校准日期 / 截距 / 测量显示值 |
| `T_MEASURINGRANGE` |  | 测量范围 / 示值修正量 / 测量显示值 |
| `T_MEASURINGVALUE` |  | 测量范围 / 示值修正量 / 测量显示值 |
| `WORKINGORDERCODE` |  |  |
| `CALCULATIONMETHOD` | 加热方式 |  |
| `P_CORRECTIONVALUE` |  |  |
| `T_CORRECTIONVALUE` |  | 测量范围 / 示值修正量 / 测量显示值 |
| `D_CALIBRATEDATENEXT` |  | 下一次 / 标准气 |
| `D_CALIBRATEDATEPREV` |  | 流量检查日期 / 上一次 / 零气 |
| `F_CALIBRATIONRANGE1` |  | 零气 |
| `F_CALIBRATIONRANGE2` |  | 标准气 |
| `P_CALIBRATEDATENEXT` |  | 下次校准日期 / 截距 / 真实值(Pa) |
| `P_CALIBRATEDATEPREV` |  | 上次校准日期 / 截距 / 测量显示值 |
| `T_CALIBRATEDATENEXT` |  | 上次校准日期 / 下次校准日期 / 真实值(Ta) |
| `T_CALIBRATEDATEPREV` |  | 上次校准日期 / 下次校准日期 / 真实值(Ta) |
| `F_CALIBRATEDATENEXT1` |  | 零气 |
| `F_CALIBRATEDATENEXT2` |  | 标准气 |
| `F_CALIBRATEDATEPREV1` |  | 零气 |
| `F_CALIBRATEDATEPREV2` |  | 标准气 |
| `D_CALIBRATIONEQUATION` |  |  |
| `F_CALIBRATIONEQUATION` |  |  |
| `P_CALIBRATIONEQUATION` |  |  |

**平台校验器：**`DF_QM_20`=required；`DF_QM_35`=required；`DF_QM_50`=required；`DF_QM_60`=required；`DF_QM_80`=required；`DF_QM_85`=required；`DF_VALUVE_20`=required；`DF_VALUVE_35`=required；`DF_VALUVE_50`=required；`DF_VALUVE_60`=required；`DF_VALUVE_80`=required；`DF_VALUVE_85`=required；`D_AC1`=required；`D_AC2`=required；`D_BC1`=required；`D_BC2`=required；`D_DEVICEMODEL`=required；`D_FACTORYCODE`=required；`D_RC1`=required；`D_RC2`=required；`F_AS1`=required；`F_AS2`=required；`F_BS1`=required；`F_BS2`=required；`F_CALIBRATIONRANGE1`=required；`F_CALIBRATIONRANGE2`=required；`F_DEVICEMODEL1`=required；`F_DEVICEMODEL2`=required；`F_FACTORYCODE1`=required；`F_FACTORYCODE2`=required；`F_RS1`=required；`F_RS2`=required；`HUMIDITY`=required；`P_AS`=required；`P_BS`=required；`P_DEVICEMODEL`=required；`P_FACTORYCODE`=required；`P_MEASURINGVALUE`=required；`P_PA`=required；`P_RS`=required；`RF_D_20`=required；`RF_D_35`=required；`RF_D_50`=required；`RF_D_60`=required；`RF_D_80`=required；`RF_D_85`=required；`RF_QA_20`=required；`RF_QA_35`=required；`RF_QA_50`=required；`RF_QA_60`=required；`RF_QA_80`=required；`RF_QA_85`=required；`RF_QS_20`=required；`RF_QS_35`=required；`RF_QS_50`=required；`RF_QS_60`=required；`RF_QS_80`=required；`RF_QS_85`=required；`RF_VALUVE_20`=required；`RF_VALUVE_35`=required；`RF_VALUVE_50`=required；`RF_VALUVE_60`=required；`RF_VALUVE_80`=required；`RF_VALUVE_85`=required；`TEMPERATURE`=required；`T_CORRECTIONVALUE`=required；`T_DEVICEMODEL`=required；`T_FACTORYCODE`=required；`T_MEASURINGRANGE`=required；`T_MEASURINGVALUE`=required；`T_TA`=required

## RF_Q_LONGOPTICALPATH_NO2
- 实体文件：`ReportForms/RF_Q_LONGOPTICALPATH_NO2.cs`
- 视图：Views/ReportForms/RF_Q_LongOpticalPath_NO2.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `TAMB` | 环境温度 | 环境温度（℃） / 环境压力（kPa） |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 | 备注： |
| `SCBMPA` | 标定前标气压力 | 标定前标气压力（Mpa） / 标定后标气压力（Mpa） |
| `SCCODE` | 标气瓶编号 | 仪器编号 / 标气瓶编号 |
| `SCDATE` | 标气有效期 | 标气有效期 / 标气浓度 |
| `SCOMPA` | 标定后标气压力 | 标定前标气压力（Mpa） / 标定后标气压力（Mpa） |
| `PRESSURE` | 环境压力 | 环境温度（℃） / 环境压力（kPa） |
| `SCDENSITY` | 标气浓度 | 标气有效期 / 标气浓度 |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 | 仪器编号 / 标气瓶编号 |
| `DEVICENAME` | 监测仪器名称 | 监测仪器名称 / 校准日期 |
| `REVIEWDATE` | 复核时间 |  |
| `SIZE1VALUE` | 样品池长度 |  |
| `SIZE2VALUE` | 样品池长度 |  |
| `SIZE3VALUE` | 样品池长度 |  |
| `SIZE4VALUE` | 样品池长度 |  |
| `SIZE5VALUE` | 样品池长度 |  |
| `SIZE6VALUE` | 样品池长度 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `DENSITY1VALUE` | 输入标气浓度 |  |
| `DENSITY2VALUE` | 输入标气浓度 |  |
| `DENSITY3VALUE` | 输入标气浓度 |  |
| `DENSITY4VALUE` | 输入标气浓度 |  |
| `DENSITY5VALUE` | 输入标气浓度 |  |
| `DENSITY6VALUE` | 输入标气浓度 |  |
| `OPTPATH1VALUE` | 光程 |  |
| `OPTPATH2VALUE` | 光程 |  |
| `OPTPATH3VALUE` | 光程 |  |
| `OPTPATH4VALUE` | 光程 |  |
| `OPTPATH5VALUE` | 光程 |  |
| `OPTPATH6VALUE` | 光程 |  |
| `OLICHECK1VALUE` | 外光光强（外光光强）检查值 | 外光光强（外光光强） / &gt;30000（或说明书中标称的特定百分比） |
| `PREPARERUSERID` | 填表人 |  |
| `RESPONSE1VALUE` | 响应值 |  |
| `RESPONSE2VALUE` | 响应值 |  |
| `RESPONSE3VALUE` | 响应值 |  |
| `RESPONSE4VALUE` | 响应值 |  |
| `RESPONSE5VALUE` | 响应值 |  |
| `RESPONSE6VALUE` | 响应值 |  |
| `CALIBRATIONDATE` | 校准日期 | 监测仪器名称 / 校准日期 |
| `EQDENSITY1VALUE` | 等效浓度 |  |
| `EQDENSITY2VALUE` | 等效浓度 |  |
| `EQDENSITY3VALUE` | 等效浓度 |  |
| `EQDENSITY4VALUE` | 等效浓度 |  |
| `EQDENSITY5VALUE` | 等效浓度 |  |
| `EQDENSITY6VALUE` | 等效浓度 |  |
| `MICDCHECK2VALUE` | 汞灯通道偏差检查值 | 汞灯通道偏差 / ±3 |
| `OLICHECK1REMARK` | 外光光强（外光光强）异常时处理记录 | 外光光强（外光光强） / &gt;30000（或说明书中标称的特定百分比） |
| `RFWINSPECTIONID` | 流水号 |  |
| `CALIBRATIONBSPAN` | 校准前Span | 校准前Offset |
| `CALIBRATIONOSPAN` | 校准后Span | 校准后Span / 校准后offset |
| `MICDCHECK2REMARK` | 汞灯通道偏差异常时处理记录 | 汞灯通道偏差 / ±3 |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `SCORESPONSE1VALUE` | 校准后响应值 |  |
| `SCORESPONSE2VALUE` | 校准后响应值 |  |
| `SCORESPONSE3VALUE` | 校准后响应值 |  |
| `SCORESPONSE4VALUE` | 校准后响应值 |  |
| `SCORESPONSE5VALUE` | 校准后响应值 |  |
| `SCORESPONSE6VALUE` | 校准后响应值 |  |
| `CALIBRATIONBOFFSET` | 校准前Offset | 校准前Offset |
| `CALIBRATIONOOFFSET` | 校准后offset | 校准后Span / 校准后offset |

**平台校验器：**`CALIBRATIONBOFFSET`=required；`CALIBRATIONBSPAN`=required；`CALIBRATIONOOFFSET`=required；`CALIBRATIONOSPAN`=required；`DEVICECODE`=required；`DEVICENAME`=required；`MICDCHECK2VALUE`=required；`OLICHECK1VALUE`=required；`PRESSURE`=required；`SCBMPA`=required；`SCCODE`=required；`SCDENSITY`=required；`SCOMPA`=required；`TAMB`=required

## RF_Q_LONGOPTICALPATH_O3
- 实体文件：`ReportForms/RF_Q_LONGOPTICALPATH_O3.cs`
- 视图：Views/ReportForms/RF_Q_LongOpticalPath_O3.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `TAMB` | 环境温度 | 环境温度（℃） / 环境压力（kPa） |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 | 备注： |
| `PRESSURE` | 环境压力 | 环境温度（℃） / 环境压力（kPa） |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 | 监测仪器编号 / 标准臭氧发生器型号 |
| `REVIEWDATE` | 复核时间 |  |
| `SIZE1VALUE` | 样品池长度 |  |
| `SIZE2VALUE` | 样品池长度 |  |
| `SIZE3VALUE` | 样品池长度 |  |
| `SIZE4VALUE` | 样品池长度 |  |
| `SIZE5VALUE` | 样品池长度 |  |
| `SIZE6VALUE` | 样品池长度 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 监测仪器名称 | 监测仪器型号 / 校准日期 |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `DENSITY1VALUE` | 输入标气浓度 |  |
| `DENSITY2VALUE` | 输入标气浓度 |  |
| `DENSITY3VALUE` | 输入标气浓度 |  |
| `DENSITY4VALUE` | 输入标气浓度 |  |
| `DENSITY5VALUE` | 输入标气浓度 |  |
| `DENSITY6VALUE` | 输入标气浓度 |  |
| `GENERATORCODE` | 标准臭氧发生器编号 | 标准臭氧发生器编号 / &nbsp; / &nbsp; |
| `OPTPATH1VALUE` | 光程 |  |
| `OPTPATH2VALUE` | 光程 |  |
| `OPTPATH3VALUE` | 光程 |  |
| `OPTPATH4VALUE` | 光程 |  |
| `OPTPATH5VALUE` | 光程 |  |
| `OPTPATH6VALUE` | 光程 |  |
| `GENERATORMODEL` | 标准臭氧发生器型号 | 监测仪器编号 / 标准臭氧发生器型号 |
| `OLICHECK1VALUE` | 外光光强（外光光强）检查值 | 外光光强（外光光强） / &gt;30000（或说明书中标称的特定百分比） |
| `PREPARERUSERID` | 填表人 |  |
| `RESPONSE1VALUE` | 响应值 |  |
| `RESPONSE2VALUE` | 响应值 |  |
| `RESPONSE3VALUE` | 响应值 |  |
| `RESPONSE4VALUE` | 响应值 |  |
| `RESPONSE5VALUE` | 响应值 |  |
| `RESPONSE6VALUE` | 响应值 |  |
| `CALIBRATIONDATE` | 校准日期 | 监测仪器型号 / 校准日期 |
| `EQDENSITY1VALUE` | 等效浓度 |  |
| `EQDENSITY2VALUE` | 等效浓度 |  |
| `EQDENSITY3VALUE` | 等效浓度 |  |
| `EQDENSITY4VALUE` | 等效浓度 |  |
| `EQDENSITY5VALUE` | 等效浓度 |  |
| `EQDENSITY6VALUE` | 等效浓度 |  |
| `MICDCHECK2VALUE` | 汞灯通道偏差检查值 | 汞灯通道偏差 / ±3 |
| `OLICHECK1REMARK` | 外光光强（外光光强）异常时处理记录 | 外光光强（外光光强） / &gt;30000（或说明书中标称的特定百分比） |
| `RFWINSPECTIONID` | 流水号 |  |
| `CALIBRATIONBSPAN` | 校准前Span | 校准前Offset |
| `CALIBRATIONOSPAN` | 校准后Span | 校准后Span / 校准后offset |
| `MICDCHECK2REMARK` | 汞灯通道偏差异常时处理记录 | 汞灯通道偏差 / ±3 |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `SCORESPONSE1VALUE` | 校准后响应值 |  |
| `SCORESPONSE2VALUE` | 校准后响应值 |  |
| `SCORESPONSE3VALUE` | 校准后响应值 |  |
| `SCORESPONSE4VALUE` | 校准后响应值 |  |
| `SCORESPONSE5VALUE` | 校准后响应值 |  |
| `SCORESPONSE6VALUE` | 校准后响应值 |  |
| `CALIBRATIONBOFFSET` | 校准前Offset | 校准前Offset |
| `CALIBRATIONOOFFSET` | 校准后offset | 校准后Span / 校准后offset |

**平台校验器：**`CALIBRATIONBOFFSET`=required；`CALIBRATIONBSPAN`=required；`CALIBRATIONOOFFSET`=required；`CALIBRATIONOSPAN`=required；`DEVICECODE`=required；`DEVICEMODEL`=required；`GENERATORCODE`=required；`GENERATORMODEL`=required；`MICDCHECK2VALUE`=required；`OLICHECK1VALUE`=required；`PRESSURE`=required；`TAMB`=required

## RF_Q_LONGOPTICALPATH_SO2
- 实体文件：`ReportForms/RF_Q_LONGOPTICALPATH_SO2.cs`
- 视图：Views/ReportForms/RF_Q_LongOpticalPath_SO2.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `TAMB` | 环境温度 | 环境温度（℃） / 环境压力（kPa） |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 | 备注： |
| `SCBMPA` | 标定前标气压力 | 标定前标气压力（Mpa） / 标定后标气压力（Mpa） |
| `SCCODE` | 标气瓶编号 | 仪器编号 / 标气瓶编号 |
| `SCDATE` | 标气有效期 | 标气有效期 / 标气浓度 |
| `SCOMPA` | 标定后标气压力 | 标定前标气压力（Mpa） / 标定后标气压力（Mpa） |
| `PRESSURE` | 环境压力 | 环境温度（℃） / 环境压力（kPa） |
| `SCDENSITY` | 标气浓度 | 标气有效期 / 标气浓度 |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 | 仪器编号 / 标气瓶编号 |
| `DEVICENAME` | 监测仪器名称 | 监测仪器名称 / 校准日期 |
| `REVIEWDATE` | 复核时间 |  |
| `SIZE1VALUE` | 样品池长度 |  |
| `SIZE2VALUE` | 样品池长度 |  |
| `SIZE3VALUE` | 样品池长度 |  |
| `SIZE4VALUE` | 样品池长度 |  |
| `SIZE5VALUE` | 样品池长度 |  |
| `SIZE6VALUE` | 样品池长度 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `DENSITY1VALUE` | 输入标气浓度 |  |
| `DENSITY2VALUE` | 输入标气浓度 |  |
| `DENSITY3VALUE` | 输入标气浓度 |  |
| `DENSITY4VALUE` | 输入标气浓度 |  |
| `DENSITY5VALUE` | 输入标气浓度 |  |
| `DENSITY6VALUE` | 输入标气浓度 |  |
| `OPTPATH1VALUE` | 光程 |  |
| `OPTPATH2VALUE` | 光程 |  |
| `OPTPATH3VALUE` | 光程 |  |
| `OPTPATH4VALUE` | 光程 |  |
| `OPTPATH5VALUE` | 光程 |  |
| `OPTPATH6VALUE` | 光程 |  |
| `OLICHECK1VALUE` | 外光光强（外光光强）检查值 | 外光光强（外光光强） / &gt;30000（或说明书中标称的特定百分比） |
| `PREPARERUSERID` | 填表人 |  |
| `RESPONSE1VALUE` | 响应值 |  |
| `RESPONSE2VALUE` | 响应值 |  |
| `RESPONSE3VALUE` | 响应值 |  |
| `RESPONSE4VALUE` | 响应值 |  |
| `RESPONSE5VALUE` | 响应值 |  |
| `RESPONSE6VALUE` | 响应值 |  |
| `CALIBRATIONDATE` | 校准日期 | 监测仪器名称 / 校准日期 |
| `EQDENSITY1VALUE` | 等效浓度 |  |
| `EQDENSITY2VALUE` | 等效浓度 |  |
| `EQDENSITY3VALUE` | 等效浓度 |  |
| `EQDENSITY4VALUE` | 等效浓度 |  |
| `EQDENSITY5VALUE` | 等效浓度 |  |
| `EQDENSITY6VALUE` | 等效浓度 |  |
| `MICDCHECK2VALUE` | 汞灯通道偏差检查值 | 汞灯通道偏差 / ±3 |
| `OLICHECK1REMARK` | 外光光强（外光光强）异常时处理记录 | 外光光强（外光光强） / &gt;30000（或说明书中标称的特定百分比） |
| `RFWINSPECTIONID` | 流水号 |  |
| `CALIBRATIONBSPAN` | 校准前Span | 校准前Offset |
| `CALIBRATIONOSPAN` | 校准后Span | 校准后Span / 校准后offset |
| `MICDCHECK2REMARK` | 汞灯通道偏差异常时处理记录 | 汞灯通道偏差 / ±3 |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `SCORESPONSE1VALUE` | 校准后响应值 |  |
| `SCORESPONSE2VALUE` | 校准后响应值 |  |
| `SCORESPONSE3VALUE` | 校准后响应值 |  |
| `SCORESPONSE4VALUE` | 校准后响应值 |  |
| `SCORESPONSE5VALUE` | 校准后响应值 |  |
| `SCORESPONSE6VALUE` | 校准后响应值 |  |
| `CALIBRATIONBOFFSET` | 校准前Offset | 校准前Offset |
| `CALIBRATIONOOFFSET` | 校准后offset | 校准后Span / 校准后offset |

**平台校验器：**`CALIBRATIONBOFFSET`=required；`CALIBRATIONBSPAN`=required；`CALIBRATIONOOFFSET`=required；`CALIBRATIONOSPAN`=required；`DEVICECODE`=required；`DEVICENAME`=required；`MICDCHECK2VALUE`=required；`OLICHECK1VALUE`=required；`PRESSURE`=required；`SCBMPA`=required；`SCCODE`=required；`SCDENSITY`=required；`SCOMPA`=required；`TAMB`=required

## RF_Q_PM10RUNSTATUSCHECK
- 实体文件：`ReportForms/RF_Q_PM10RUNSTATUSCHECK.cs`
- 视图：Views/ReportForms/RF_Q_Pm10RunStatusCheck.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEIVCECODE` | 仪器编号 | 仪器编号 / 检查日期 |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEIVCEMODEL` | 仪器型号(PM10) | 仪器编号 / 检查日期 |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 | 仪器编号 / 检查日期 |
| `RFWINSPECTIONID` | 流水号 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `PM10CHECKKO1VALUE` | K0值检查原始值 | K0值检查 / ≤±2% |
| `PM10CHECKKO2VALUE` | K0值检查检查值 | K0值检查 / ≤±2% |
| `PM10CHECKKO3VALUE` | K0值检查误差 | K0值检查 / ≤±2% |
| `PM10CHECKKO4VALUE` | K0值检查异常时处理记录 | K0值检查 / ≤±2% |
| `PM10CHECKTEMP1VALUE` | 标准膜检查原始值 | 标准膜检查 / ≤±2% |
| `PM10CHECKTEMP2VALUE` | 标准膜检查检查值 | 标准膜检查 / ≤±2% |
| `PM10CHECKTEMP3VALUE` | 标准膜检查误差 | 标准膜检查 / ≤±2% |
| `PM10CHECKTEMP4VALUE` | 标准膜检查异常时处理记录 | 标准膜检查 / ≤±2% |

**平台校验器：**`DEIVCECODE`=required；`DEIVCEMODEL`=required；`PM10CHECKTEMP1VALUE`=required；`PM10CHECKTEMP2VALUE`=required

## RF_Q_PM25RUNSTATUSCHECK
- 实体文件：`ReportForms/RF_Q_PM25RUNSTATUSCHECK.cs`
- 视图：Views/ReportForms/RF_Q_Pm25RunStatusCheck.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEIVCECODE` | 仪器编号 | 仪器编号 / 检查日期 |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEIVCEMODEL` | 仪器型号(PM25) | 仪器编号 / 检查日期 |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 | 仪器编号 / 检查日期 |
| `RFWINSPECTIONID` | 流水号 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `PM25CHECKKO1VALUE` | K0值检查原始值 | K0值检查 / ≤±2% |
| `PM25CHECKKO2VALUE` | K0值检查检查值 | K0值检查 / ≤±2% |
| `PM25CHECKKO3VALUE` | K0值检查误差 | K0值检查 / ≤±2% |
| `PM25CHECKKO4VALUE` | K0值检查异常时处理记录 | K0值检查 / ≤±2% |
| `PM25CHECKTEMP1VALUE` | 标准膜检查原始值 | 标准膜检查 / ≤±2% |
| `PM25CHECKTEMP2VALUE` | 标准膜检查检查值 | 标准膜检查 / ≤±2% |
| `PM25CHECKTEMP3VALUE` | 标准膜检查误差 | 标准膜检查 / ≤±2% |
| `PM25CHECKTEMP4VALUE` | 标准膜检查异常时处理记录 | 标准膜检查 / ≤±2% |

**平台校验器：**`DEIVCECODE`=required；`DEIVCEMODEL`=required；`PM25CHECKTEMP1VALUE`=required；`PM25CHECKTEMP2VALUE`=required

## RF_Q_PMPRESSURE
- 实体文件：`ReportForms/RF_Q_PMPRESSURE.cs`
- 视图：Views/ReportForms/RF_Q_PmPressure.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 | 校准日期 |
| `RFWINSPECTIONID` | 流水号 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `PM10CHECKPRES1VALUE` | PM10气压仪器显示 | 气压 |
| `PM10CHECKPRES2VALUE` | PM10气压标准值（实际值） | 气压 |
| `PM10CHECKPRES3VALUE` | PM10气压误差 | 气压 |
| `PM10CHECKPRES4VALUE` | PM10气压校准情况 | 气压 |
| `PM10CHECKTEMP1VALUE` | PM10气温仪器显示 | PM10分析仪 / 气温 |
| `PM10CHECKTEMP2VALUE` | PM10气温标准值（实际值） | PM10分析仪 / 气温 |
| `PM10CHECKTEMP3VALUE` | PM10气温误差 | PM10分析仪 / 气温 |
| `PM10CHECKTEMP4VALUE` | PM10气温校准情况 | PM10分析仪 / 气温 |
| `PM25CHECKPRES1VALUE` | PM25气压仪器显示 | 气压 |
| `PM25CHECKPRES2VALUE` | PM25气温标准值（实际值） | 气压 |
| `PM25CHECKPRES3VALUE` | PM25气温误差 | 气压 |
| `PM25CHECKPRES4VALUE` | PM25气温校准情况 | 气压 |
| `PM25CHECKTEMP1VALUE` | PM25气温仪器显示 | PM2.5分析仪 / 气温 |
| `PM25CHECKTEMP2VALUE` | PM25气温标准值（实际值） | PM2.5分析仪 / 气温 |
| `PM25CHECKTEMP3VALUE` | PM25气温误差 | PM2.5分析仪 / 气温 |
| `PM25CHECKTEMP4VALUE` | PM25气温校准情况 | PM2.5分析仪 / 气温 |

**平台校验器：**`PM10CHECKPRES1VALUE`=required；`PM10CHECKPRES2VALUE`=required；`PM10CHECKTEMP1VALUE`=required；`PM10CHECKTEMP2VALUE`=required；`PM25CHECKPRES1VALUE`=required；`PM25CHECKPRES2VALUE`=required；`PM25CHECKTEMP1VALUE`=required；`PM25CHECKTEMP2VALUE`=required

## RF_Q_PMRUNSTATUSCHECK
- 实体文件：`ReportForms/RF_Q_PMRUNSTATUSCHECK.cs`
- 视图：Views/ReportForms/RF_Q_PmRunStatusCheck.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `CHECKTYPE` | 检查类型(PM10/PM25) |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEIVCECODE` | 仪器编号 | 仪器编号 / 检查日期 |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEIVCEMODEL` | 仪器型号(PM10) | 仪器编号 / 检查日期 |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` |  |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 | 仪器编号 / 检查日期 |
| `PMCHECKKO1VALUE` | K0值检查原始值 | K0值检查 / ≤±2% |
| `PMCHECKKO2VALUE` | K0值检查检查值 | K0值检查 / ≤±2% |
| `PMCHECKKO3VALUE` | K0值检查误差 | K0值检查 / ≤±2% |
| `PMCHECKKO4VALUE` | K0值检查异常时处理记录 | K0值检查 / ≤±2% |
| `RFWINSPECTIONID` | 流水号 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `PMCHECKTEMP1VALUE` | 标准膜检查原始值 | 标准膜检查 / ≤±2% |
| `PMCHECKTEMP2VALUE` | 标准膜检查检查值 | 标准膜检查 / ≤±2% |
| `PMCHECKTEMP3VALUE` | 标准膜检查误差 | 标准膜检查 / ≤±2% |
| `PMCHECKTEMP4VALUE` | 标准膜检查异常时处理记录 | 标准膜检查 / ≤±2% |

**平台校验器：**`DEIVCECODE`=required；`DEIVCEMODEL`=required；`PMCHECKTEMP1VALUE`=required；`PMCHECKTEMP2VALUE`=required

## RF_Q_STATIONDEVICECLEAN
- 实体文件：`ReportForms/RF_Q_StationDeviceClean.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CHECK1DATE` | 清洁采样总管维护时间 |  |
| `CHECK2DATE` | 清洁采样支管维护时间 |  |
| `CHECK3DATE` | 清洁采样风机维护时间 |  |
| `CHECK4DATE` | 清洁颗粒物采样管维护时间 |  |
| `CHECK5DATE` | 清洁角反射镜（长光程）维护时间 |  |
| `CHECK6DATE` |  |  |
| `CHECK7DATE` |  |  |
| `CHECK8DATE` |  |  |
| `CHECK9DATE` |  |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `CHACK1USERID` | 清洁采样总管巡检人 |  |
| `CHACK2USERID` | 清洁采样支管巡检人 |  |
| `CHACK3USERID` | 清洁采样风机巡检人 |  |
| `CHACK4USERID` | 清洁颗粒物采样管巡检人 |  |
| `CHACK5USERID` | 清洁角反射镜（长光程）巡检人 |  |
| `CHACK6USERID` |  |  |
| `CHACK7USERID` |  |  |
| `CHACK8USERID` |  |  |
| `CHACK9USERID` |  |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `RFWINSPECTIONID` | 流水号 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |

## RF_Q_StationMaintainCheck
- 实体文件：`ReportForms/RF_Q_StationMaintainCheck.cs`
- 视图：Views/ReportForms/RF_Q_StationMaintainCheck.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `YEAR` | 年 | 年份： / 季度： |
| `CFJRK` | 清洗采样总管及采样风机 备注 | 1 / 清洗采样总管及采样风机 |
| `AREAID` |  |  |
| `PM10RK` | PM10 备注 | 2 / PM10 监测仪器进行标准膜校准 或K0值检查 |
| `PM25RK` | PM25 备注 | 3 / PM2.5 监测仪器进行标准膜校准 或K0值检查 |
| `REMARK` |  |  |
| `CFJGZQK` | 清洗采样总管及采样风机 工作情况 | 1 / 清洗采样总管及采样风机 |
| `CFJUSER` | 清洗采样总管及采样风机 运维人员 |  |
| `QUARTER` | 第几季度 |  |
| `PM10GZQK` | PM10 工作情况 | 2 / PM10 监测仪器进行标准膜校准 或K0值检查 |
| `PM10USER` | PM10 运维人员 |  |
| `PM25GZQK` | PM25 工作情况 | 3 / PM2.5 监测仪器进行标准膜校准 或K0值检查 |
| `PM25USER` | PM25 运维人员 |  |
| `CHECKDATE` |  |  |
| `STATIONID` |  |  |
| `CREATEDATE` |  |  |
| `REVIEWDATE` |  |  |
| `AUDITORDATE` |  |  |
| `PROCESSTYPE` |  |  |
| `PREPARERDATE` |  |  |
| `REVIEWUSERID` |  |  |
| `AUDITORUSERID` |  |  |
| `POLLUTANTTYPE` |  |  |
| `PREPARERUSERID` |  |  |
| `OPERATIONSUNITID` |  |  |
| `WORKINGORDERCODE` |  |  |
| `STATIONMAINTAINCHECKID` |  |  |

**平台校验器：**`CFJGZQK`=required；`PM10GZQK`=required；`PM25GZQK`=required

## RF_RULE
- 实体文件：`ReportForms/RF_RULE.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `RULENAME` |  |  |
| `RULETYPE` |  |  |
| `RULECYCLE` |  |  |
| `RULETIMES` |  |  |
| `REMINDERDAYS` |  |  |

## RF_RULEITEM
- 实体文件：`ReportForms/RF_RULEITEM.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `SHORTNAME` |  |  |
| `RULEITEMTAG` |  |  |
| `RULEITEMNAME` |  |  |
| `POLLUTANTTYPE` |  |  |
| `PLANFINISHTIME` |  |  |

## RF_RULEITEM_RELEVANCE
- 实体文件：`ReportForms/RF_RULEITEM_RELEVANCE.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `RULETYPE` |  |  |
| `USERTYPE` |  |  |
| `RULEITEMTAG` |  |  |

## RF_RuleItemTask
- 实体文件：`ReportForms/RF_RuleItemTask.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `ISOVER` |  |  |
| `TASKNUM` |  |  |
| `DEVICEID` |  |  |
| `DIFFDAYS` |  |  |
| `MONTHNUM` |  |  |
| `NEXTDATE` |  |  |
| `PREVDATE` |  |  |
| `RULETYPE` |  |  |
| `BRANDCODE` |  |  |
| `MONTHSPAN` |  |  |
| `STATIONID` |  |  |
| `CURRENTDATE` |  |  |
| `RULEITEMTAG` |  |  |
| `RULEITEMNAME` |  |  |
| `POLLUTANTTYPE` |  |  |
| `PREVORDERCODE` |  |  |
| `CURRENTORDERCODE` |  |  |

## RF_SEC_APPLICATIONFORM
- 实体文件：`ReportForms/RF_SEC_APPLICATIONFORM.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `DYSX` | 调研事项 |  |
| `SPYJ` | 总站意见 |  |
| `SQRQ` | 申请日期 |  |
| `AREAID` | 省市区 |  |
| `DYDWRY` | 调研单位以及人员 |  |
| `REMARK` | 备注 |  |
| `SQDWID` | 申请单位 |  |
| `STATUS` | 状态 0保存 1 （待审核） 2（已审核） |  |
| `EDTTIME` | 调研结束时间 |  |
| `ISAGREE` | 是否同意 0同意 1不同意 |  |
| `SDTTIME` | 调研开始时间 |  |
| `PHYWGSID` | 配合运维公司 |  |
| `CHECKDATE` | 检查时间 |  |
| `DYSTATION` | 调研站点 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `SQDWPZPATH` | 申请凭证 |  |
| `SUBMITDATE` | 提交时间 |  |
| `UPDATETIME` | 最后更新时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `SUBMITUSERID` | 提交人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `APPLICATIONFORMID` |  |  |

## RF_SEC_GASEOUSCHECK
- 实体文件：`ReportForms/RF_SEC_GASEOUSCHECK.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `COR` | COR |  |
| `NOR` | NOR |  |
| `O3R` | O3R |  |
| `COJJ` | CO截距 |  |
| `COWC` | CO误差 |  |
| `COXL` | CO斜率 |  |
| `NO2R` | NO2R |  |
| `NOJJ` | NO截距 |  |
| `NOWC` | NO误差 |  |
| `NOXL` | NOX斜率 |  |
| `NOXR` | NOXR |  |
| `O3JJ` | O3截距 |  |
| `O3WC` | O3误差 |  |
| `O3XL` | O3斜率 |  |
| `SO2R` | SO2R |  |
| `NO2JJ` | NO2截距 |  |
| `NO2WC` | NO2误差 |  |
| `NO2XL` | NO2斜率 |  |
| `NOXJJ` | NOX截距 |  |
| `NOXWC` | NOX误差 |  |
| `NOXXL` | NOX斜率 |  |
| `SO2JJ` | SO2截距 |  |
| `SO2WC` | SO2误差 |  |
| `SO2XL` | SO2斜率 |  |
| `AREAID` | 省市区 |  |
| `COREAMK` | CO备注 |  |
| `NOREAMK` | NO备注 |  |
| `O3REAMK` | O3备注 |  |
| `NO2REAMK` | NO2备注 |  |
| `NOXREAMK` | NOX备注 |  |
| `SO2REAMK` | SO2备注 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFSECGASEOUSCHECKID` | 主键 |  |

## RF_SEC_INSPECTION
- 实体文件：`SEC/RF_SEC_INSPECTION.cs`
- 视图：Views/ReportForms/RF_SEC_INSPECTION.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `CITYID` | 城市 |  |
| `REMARK` | 备注 |  |
| `INSIDE9` | 站房环境卫生是否合格 | 9 / 站房环境卫生是否合格 |
| `INSIDE10` | 消防器材是否在使用有效期内 | 10 / 消防器材是否在使用有效期内 |
| `INSIDE11` | 站房内部的供电、通讯是否畅通 | 11 / 站房内部的供电、通讯是否畅通 |
| `INSIDE12` | 站房内部给排水、供暖设施、空调工作状况 | 12 / 站房内部给排水、供暖设施、空调工作状况 |
| `INSIDE13` | 站房内有无气泵产生的异常声音 | 13 / 站房内有无气泵产生的异常声音 |
| `INSIDE14` | 站房内有无异常气味 | 14 / 站房内有无异常气味 |
| `INSIDE15` | 自动监测室内温度、湿度是否符合要求 | 15 / 自动监测室内温度、湿度是否符合要求 |
| `INSIDE16` | 气体采样管路是否由于室外温差产生冷凝水 | 16 / 气体采样管路是否由于室外温差产生冷凝水 |
| `INSIDE17` | 排风扇是否正常运行 | 17 / 排风扇是否正常运行 |
| `INSIDE18` | 稳压电源参数是否正常 | 18 / 稳压电源参数是否正常 |
| `INSIDE19` | 各电源插头、线板工作是否正常 | 19 / 各电源插头、线板工作是否正常 |
| `INSIDE20` | 检查清洁采样头、颗粒物切割头，清理滤水瓶积水 | 20 / 检查清洁采样头、颗粒物切割头，清理滤水瓶积水 |
| `INSIDE21` | 仪器气泵工作是否正常 | 21 / 仪器气泵工作是否正常 |
| `INSIDE22` | 检查/更换干燥剂：蓝色变为粉红时显示失效程度，蓝色剩1/3～1/4 时即应更换。 ///(干燥剂-变色硅胶的处理方法：放在表面皿/搪瓷盘中在烘箱120°C烘干，时间为4小时左右;烘干后放在干燥器中保存) | 22 / 检查/更换干燥剂：蓝色变为粉红时显示失效程度，蓝色剩1/3～1/4 时即应更换。 (干燥剂-变色硅胶的处理方法：放在表面皿/搪瓷盘中在烘箱120°C烘干，时间为4小时左右;烘干后放在干燥器中保存) |
| `INSIDE23` | 检查钢瓶气及减压阀安全情况 | 23 / 检查钢瓶气及减压阀安全情况 |
| `INSIDE24` | 检查采样总管和支管有无冷凝水或污物 | 24 / 检查采样总管和支管有无冷凝水或污物 |
| `INSIDE25` | 检查/更换颗粒物分析仪滤带或TEOM采样滤膜 | 25 / 检查/更换颗粒物分析仪滤带或TEOM采样滤膜 |
| `OUTSIDE1` | 点位周围环境变化情况 | 1 / 点位周围环境变化情况 |
| `OUTSIDE2` | 点位周围安全隐患 | 2 / 点位周围安全隐患 |
| `OUTSIDE3` | 点位周围道路、供电线路、通讯线路、给排水设施完好或损坏状况 | 3 / 点位周围道路、供电线路、通讯线路、给排水设施完好或损坏状况 |
| `OUTSIDE4` | 站房外围的防护栏、隔离带有无损坏情况 | 4 / 站房外围的防护栏、隔离带有无损坏情况 |
| `OUTSIDE5` | 监控视屏是否运行正常和清洁 | 5 / 监控视屏是否运行正常和清洁 |
| `OUTSIDE6` | 周围树木是否需要修剪 | 6 / 周围树木是否需要修剪 |
| `OUTSIDE7` | 站房防雷接地是否完好 | 7 / 站房防雷接地是否完好 |
| `OUTSIDE8` | 站房屋顶是否完好，有无漏雨 | 8 / 站房屋顶是否完好，有无漏雨 |
| `CHECKDATE` | 检查时间 | 运维单位： / 现场检查单位： / 检查时间： |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `FIELDUNITID` | 现场单位ID |  |
| `PROCESSTYPE` |  |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` |  |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFSECINSPECTIONID` | 主键 |  |

## RF_SEC_INSTRUMENTRECORD
- 实体文件：`ReportForms/RF_SEC_INSTRUMENTRECORD.cs`
- 视图：Views/ReportForms/RF_SEC_INSTRUMENTRECORD.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `LLXH` | 流量计型号 | 流量计 |
| `QYXH` | 气压计型号 | 气压计 |
| `TEMP` | 温度 | 环境条件 |
| `WDXH` | 温度计型号 | 温度计 |
| `OTHER` | 其它 | 环境条件 |
| `AREAID` | 省市区 |  |
| `JZBZQY` | 温度、气压校准标准气压计 | 标准气压计 / 仪器显示气压 / 仪器显示气压 |
| `JZBZWD` | 温度、气压校准标准温度计 | 标准温度计 / 仪器显示温度 / 仪器显示温度 |
| `LLJDRQ` | 流量计检定日期 | 流量计 |
| `LLZNBH` | 流量计站内编号 | 流量计 |
| `QYJDRQ` | 气压计检定日期 | 气压计 |
| `QYZNBH` | 气压计站内编号 | 气压计 |
| `REMARK` | 备注 | 备注 |
| `WDJDRQ` | 温度计检定日期 | 温度计 |
| `WDZNBH` | 温度计站内编号 | 温度计 |
| `JLFLLBG` | 检漏辅流量泵关 | 辅流量读数[L/min.] |
| `JLFLLBK` | 检漏辅流量泵开 | 辅流量读数[L/min.] |
| `JLZLLBG` | 检漏主流量泵关 | 主流量读数[L/min.] |
| `JLZLLBK` | 检漏主流量泵开 | 主流量读数[L/min.] |
| `CSJCSFKG` | 是否合格 |  |
| `CSJCWCK0` | 误差% |  |
| `CSJCXSK0` | 显示K0 |  |
| `HUMIDITY` | 湿度 | 环境条件 |
| `JLFLLJDS` | 检漏辅流量净读数 | 辅流量读数[L/min.] |
| `JLZLLJDS` | 检漏主流量净读数 | 主流量读数[L/min.] |
| `QYJCBZQY` | 气压检查标准气压计读数 | 标准温度计读数 / 标准气压计读数 |
| `QYJCSFHG` | 气压检查是否合格 | 是否合格 / 是否合格 |
| `QYJCYQXS` | 气压检查仪器显示读数 | 温度 检查 / 仪器显示温度 / 气压 检查 / 仪器显示读数 |
| `WDJCBZWD` | 温度检查标准温度计读数 | 标准温度计读数 / 标准气压计读数 |
| `WDJCSFHG` | 温度检查是否合格 | 是否合格 / 是否合格 |
| `WDJCYQXS` | 温度检查仪器显示温度 | 温度 检查 / 仪器显示温度 / 气压 检查 / 仪器显示读数 |
| `CHECKDATE` | 检查时间 |  |
| `JLFLLSFHG` | 检漏辅流量是否合格 | 辅流量读数[L/min.] |
| `JLZLLSFHG` | 检漏主流量是否合格 | 主流量读数[L/min.] |
| `JQHYQXSQY` | 校准后仪器显示气压 | 标准气压计 / 仪器显示气压 / 仪器显示气压 |
| `JQHYQXSWD` | 校准后仪器显示温度 | 标准温度计 / 仪器显示温度 / 仪器显示温度 |
| `JZQYQXSQY` | 校准前仪器显示气压 | 标准气压计 / 仪器显示气压 / 仪器显示气压 |
| `JZQYQXSWD` | 校准前仪器显示温度 | 标准温度计 / 仪器显示温度 / 仪器显示温度 |
| `LLJCZSDPC` | 流量检查总流量设定流量偏差 | 总流量 |
| `LLJCZSFHG` | 流量检查总流量是否合格 | 总流量 |
| `LLJCZXSPC` | 流量检查总流量显示流量偏差 | 总流量 |
| `LLJCZYQLL` | 流量检查总流量仪器示值流量 | 总流量 |
| `LLJZFYQSZ` | 流量校准辅流量仪器设定流量 | 辅流量 |
| `LLJZZYQSZ` | 流量校准主流量仪器设定流量 | 主流量 |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `CSJCJZCSK0` | 校准常数K0 |  |
| `DEVICECODE` | 仪器型号 | 仪器型号 / 出厂编号 |
| `LLJCZBZXZH` | 流量检查总流量标准流量计修正后 | 总流量 |
| `LLJCZBZXZQ` | 流量检查总流量标准流量计修正前 | 总流量 |
| `LLJCZHSDPC` | 流量检查主流量设定流量偏差 | 主流量 |
| `LLJCZHSFHG` | 流量检查主流量是否合格 | 主流量 |
| `LLJCZHXSPC` | 流量检查主流量显示流量偏差 | 主流量 |
| `LLJCZHYQLL` | 流量检查主流量仪器示值流量 | 主流量 |
| `LLJZFYQSZ1` | 流量校准辅流量仪器设定流量1 |  |
| `LLJZFYQSZ2` | 流量校准辅流量仪器设定流量2 |  |
| `LLJZZYQSZ1` | 流量校准主流量仪器设定流量1 |  |
| `LLJZZYQSZ2` | 流量校准主流量仪器设定流量2 |  |
| `QYJCREMARK` |  |  |
| `REVIEWDATE` | 复核时间 |  |
| `WDJCREMARK` |  |  |
| `AUDITORDATE` | 审核时间 |  |
| `JLFLLREMARK` |  |  |
| `JLZLLREMARK` |  |  |
| `LLJCZHBZXZH` | 流量检查主流量标准流量计修正后 | 主流量 |
| `LLJCZHBZXZQ` | 流量检查主流量标准流量计修正前 | 主流量 |
| `LLJCZREMARK` |  |  |
| `LLJZFJZHXZH` | 流量校准辅流量校准后修正后 | 辅流量 |
| `LLJZFJZHXZQ` | 流量校准辅流量校准后修正前 | 辅流量 |
| `LLJZFJZQXZH` | 流量校准辅流量校准前修正后 | 辅流量 |
| `LLJZFJZQXZQ` | 流量校准辅流量校准前修正前 | 辅流量 |
| `LLJZZJZHXZH` | 流量校准主流量校准后修正后 | 主流量 |
| `LLJZZJZHXZQ` | 流量校准主流量校准后修正前 | 主流量 |
| `LLJZZJZQXZH` | 流量校准主流量校准前修正后 | 主流量 |
| `LLJZZJZQXZQ` | 流量校准主流量校准前修正前 | 主流量 |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `STATIONCODE` | 站内编号 | 子站名称 / 站内编号 |
| `LLJCZHREMARK` |  |  |
| `LLJZFJZHXZH1` | 流量校准辅流量校准后修正后1 |  |
| `LLJZFJZHXZH2` | 流量校准辅流量校准后修正后2 |  |
| `LLJZFJZHXZQ1` | 流量校准辅流量校准后修正前1 |  |
| `LLJZFJZHXZQ2` | 流量校准辅流量校准后修正前2 |  |
| `LLJZFJZQXZH1` | 流量校准辅流量校准前修正后1 |  |
| `LLJZFJZQXZH2` | 流量校准辅流量校准前修正后2 |  |
| `LLJZFJZQXZQ1` | 流量校准辅流量校准前修正前1 |  |
| `LLJZFJZQXZQ2` | 流量校准辅流量校准前修正前2 |  |
| `LLJZZJZHXZH1` | 流量校准主流量校准后修正后1 |  |
| `LLJZZJZHXZH2` | 流量校准主流量校准后修正后2 |  |
| `LLJZZJZHXZQ1` | 流量校准主流量校准后修正前1 |  |
| `LLJZZJZHXZQ2` | 流量校准主流量校准后修正前2 |  |
| `LLJZZJZQXZH1` | 流量校准主流量校准前修正后1 |  |
| `LLJZZJZQXZH2` | 流量校准主流量校准前修正后2 |  |
| `LLJZZJZQXZQ1` | 流量校准主流量校准前修正前1 |  |
| `LLJZZJZQXZQ2` | 流量校准主流量校准前修正前2 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `LEAVEFACTORYCODE` | 出厂编号 | 仪器型号 / 出厂编号 |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `INSTRUMENTRECORDID` | 主键 |  |

**平台校验器：**`CSJCJZCSK0`=required；`CSJCWCK0`=required；`CSJCXSK0`=required；`DEVICECODE`=required；`HUMIDITY`=required；`JLFLLBG`=required；`JLFLLBK`=required；`JLFLLJDS`=required；`JLZLLBG`=required；`JLZLLBK`=required；`JLZLLJDS`=required；`JQHYQXSQY`=required；`JQHYQXSWD`=required；`JZBZQY`=required；`JZBZWD`=required；`JZQYQXSQY`=required；`JZQYQXSWD`=required；`LEAVEFACTORYCODE`=required；`LLJCZBZXZH`=required；`LLJCZBZXZQ`=required；`LLJCZHBZXZH`=required；`LLJCZHBZXZQ`=required；`LLJCZHSDPC`=required；`LLJCZHXSPC`=required；`LLJCZHYQLL`=required；`LLJCZSDPC`=required；`LLJCZXSPC`=required；`LLJCZYQLL`=required；`LLJZFJZHXZH`=required；`LLJZFJZHXZH1`=required；`LLJZFJZHXZH2`=required；`LLJZFJZHXZQ`=required；`LLJZFJZHXZQ1`=required；`LLJZFJZHXZQ2`=required；`LLJZFJZQXZH`=required；`LLJZFJZQXZH1`=required；`LLJZFJZQXZH2`=required；`LLJZFJZQXZQ`=required；`LLJZFJZQXZQ1`=required；`LLJZFJZQXZQ2`=required；`LLJZFYQSZ`=required；`LLJZFYQSZ1`=required；`LLJZFYQSZ2`=required；`LLJZZJZHXZH`=required；`LLJZZJZHXZH1`=required；`LLJZZJZHXZH2`=required；`LLJZZJZHXZQ`=required；`LLJZZJZHXZQ1`=required；`LLJZZJZHXZQ2`=required；`LLJZZJZQXZH`=required；`LLJZZJZQXZH1`=required；`LLJZZJZQXZH2`=required；`LLJZZJZQXZQ`=required；`LLJZZJZQXZQ1`=required；`LLJZZJZQXZQ2`=required；`LLJZZYQSZ`=required；`LLJZZYQSZ1`=required；`LLJZZYQSZ2`=required；`LLXH`=required；`LLZNBH`=required；`OTHER`=required；`QYJCBZQY`=required；`QYJCYQXS`=required；`QYXH`=required；`QYZNBH`=required；`STATIONCODE`=required；`TEMP`=required；`WDJCBZWD`=required；`WDJCYQXS`=required；`WDXH`=required；`WDZNBH`=required

## RF_SEC_MONITORINGCHECK
- 实体文件：`ReportForms/RF_SEC_MONITORINGCHECK.cs`
- 视图：Views/ReportForms/RF_SEC_MONITORINGCHECK.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `CERQ` | 测试日期 | 测试指标 / 测试日期 |
| `CSZB` | 测试指标 | 测试指标 / 测试日期 |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 | 结论 |
| `DDJZSFHG` | 多点校准是否合格 | 多点校准 |
| `KDJCSFHG` | 24h跨度检查是否合格 | 24h跨度检查 |
| `LDJCSFHG` | 24h零点检查是否合格 | 24h零点检查 |
| `XYSJSFHG` | t90响应时间是否合格 | t90响应时间 |
| `CHECKDATE` | 检查时间 |  |
| `QMXJCSFHG` | 气密性检查是否合格 | 气密性检查 |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DDJZREMARK` | 多点校准备注 | 多点校准 |
| `DDJZRESULT` | 多点校准测试结果 | 多点校准 |
| `DEVICECODE` | 仪器型号 | 仪器名称 / 仪器型号 |
| `DEVICENAME` | 仪器名称 | 仪器名称 / 仪器型号 |
| `KDJCREMARK` | 24h跨度检查备注 | 24h跨度检查 |
| `KDJCRESULT` | 24h跨度检查测试结果 | 24h跨度检查 |
| `LDJCREMARK` | 24h零点检查备注 | 24h零点检查 |
| `LDJCRESULT` | 24h零点检查测试结果 | 24h零点检查 |
| `REVIEWDATE` | 复核时间 |  |
| `XYSJREMARK` | t90响应时间备注 | t90响应时间 |
| `XYSJRESULT` | t90响应时间测试结果 | t90响应时间 |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `QMXJCREMARK` | 气密性检查备注 | 气密性检查 |
| `QMXJCRESULT` | 气密性检查测试结果 | 气密性检查 |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `MONITORINGCHECKID` | 主键 |  |

**平台校验器：**`CSZB`=required；`DEVICECODE`=required；`DEVICENAME`=required

## RF_SEC_STATIONPROPOSAL
- 实体文件：`ReportForms/RF_SEC_STATIONPROPOSAL.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `IMG` | 附件图片 |  |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 也是建议和意见 |  |
| `STATUS` | 状态 0保存 1（待反馈） 2（已解决） |  |
| `FEEDBACK` | 反馈内容 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `SUBMITDATE` | 提交时间 |  |
| `UPDATETIME` | 最后更新时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `FEEDBACKDATE` | 反馈时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `SUBMITUSERID` | 提交人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `FEEDBACKUSERID` | 反馈人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFSECSTATIONPROPOSALID` | 主键 |  |

## RF_TW_CleanCuttingHead
- 实体文件：`ReportForms/RF_TW_CleanCuttingHead.cs`
- 视图：Views/ReportForms/RF_TW_CleanCuttingHead.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 | 备注： |
| `DEVICEID` | 仪器id |  |
| `CHECKDATE` | 检查日期 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PM_DEVICECODE` |  |  |
| `PM_DEVICETYPE` |  |  |
| `POLLUTANTTYPE` |  |  |
| `CLEANINGREMARK` |  | 清洗切割头 |
| `PM_DEVICEBRAND` |  |  |
| `PM_DEVICEMODEL` |  |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |

**平台校验器：**`CLEANINGREMARK`=required

## RF_TW_PmFlowCalibrate
- 实体文件：`ReportForms/RF_TW_PmFlowCalibrate.cs`
- 视图：Views/ReportForms/RF_TW_PmFlowCalibrate.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `F_A` |  |  |
| `F_B` |  |  |
| `F_R` |  |  |
| `AREAID` | 省市区 |  |
| `NEXT_A` |  | 校准后 |
| `NEXT_B` |  | 校准后 |
| `NEXT_C` |  | 校准后 |
| `NEXT_S` |  | 校准后 |
| `PREV_A` |  | 校准前 / 是 否 |
| `PREV_B` |  | 校准前 / 是 否 |
| `PREV_C` |  | 校准前 / 是 否 |
| `PREV_S` |  | 校准前 / 是 否 |
| `REMARK` | 备注 | 备注： |
| `CHECKEDT` |  | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| `CHECKSDT` |  | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| `DEVICEID` | 仪器id |  |
| `HUMIDITY` |  | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| `CHECKDATE` | 检查日期 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `F_NEXTDATE` |  |  |
| `F_PREVDATE` |  |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `ISCALIBRATE` |  |  |
| `PM_NEXTDATE` |  |  |
| `PM_PREVDATE` |  |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `TEMPERATURE` |  | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| `F_DEVICECODE` |  |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `F_DEVICEMODEL` |  |  |
| `PM_DEVICECODE` |  |  |
| `PM_DEVICETYPE` |  |  |
| `POLLUTANTTYPE` |  |  |
| `PM_DEVICEBRAND` |  |  |
| `PM_DEVICEMODEL` |  |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |

## RF_TW_PmFlowCheck
- 实体文件：`ReportForms/RF_TW_PmFlowCheck.cs`
- 视图：Views/ReportForms/RF_TW_PmFlowCheck.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `F_A` |  |  |
| `F_B` |  |  |
| `F_R` |  |  |
| `P_R` |  |  |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 | 备注： |
| `T_VALUE` |  | 温度计 |
| `CHECKEDT` |  | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| `CHECKSDT` |  | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| `DEVICEID` | 仪器id |  |
| `HUMIDITY` |  | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| `CHECKDATE` | 检查日期 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `F_NEXTDATE` |  |  |
| `F_PREVDATE` |  |  |
| `P_NEXTDATE` |  |  |
| `P_PREVDATE` |  |  |
| `REVIEWDATE` | 复核时间 |  |
| `T_NEXTDATE` |  | 温度计 |
| `T_PREVDATE` |  | 温度计 |
| `AUDITORDATE` | 审核时间 |  |
| `PM_NEXTDATE` |  |  |
| `PM_PREVDATE` |  |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `P_VALUEREAL` |  |  |
| `TEMPERATURE` |  | 室内温度(℃) / 室内湿度(％RH) / 开始时间 / 结束时间 |
| `F_DEVICECODE` |  |  |
| `MAINFLOWDIFF` |  | 主流量读数（l/min）_（在主流量显示屏上） |
| `MAINFLOWOPEN` |  | 主流量读数（l/min）_（在主流量显示屏上） |
| `MAINFLOWREAL` |  | 主流量真实值（l/min） |
| `MAINFLOWSTOP` |  | 主流量读数（l/min）_（在主流量显示屏上） |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `P_DEVICECODE` |  | 大气压计 |
| `REVIEWUSERID` | 复核人 |  |
| `T_DEVICECODE` |  | 温度计 |
| `AUDITORUSERID` | 审核人 |  |
| `F_DEVICEMODEL` |  |  |
| `MAINFLOWERROR` |  | 主流量设定值与修正值的相对百分误差 |
| `MAINFLOWFIXED` |  | 主流量修正值（l/min） |
| `MAINFLOWREFER` |  | 参考流量计指示的主流量值（l/min） |
| `PM_DEVICECODE` |  |  |
| `PM_DEVICETYPE` |  |  |
| `POLLUTANTTYPE` |  |  |
| `P_DEVICEMODEL` |  | 大气压计 |
| `REFERFLOWDIFF` |  | 辅流量读数（l/min）_（在主流量显示屏上） |
| `REFERFLOWOPEN` |  | 辅流量读数（l/min）_（在主流量显示屏上） |
| `REFERFLOWREAL` |  | 辅流量真实值（l/min） |
| `REFERFLOWSTOP` |  | 辅流量读数（l/min）_（在主流量显示屏上） |
| `T_DEVICEMODEL` |  | 温度计 |
| `MAINFLOWTARGET` |  | 主流量设定值（l/min）_（设定温度/流量显示屏） |
| `PM_DEVICEBRAND` |  |  |
| `PM_DEVICEMODEL` |  |  |
| `PREPARERUSERID` | 填表人 |  |
| `P_VALUEDISPLAY` |  |  |
| `REFERFLOWERROR` |  | 辅流量设定值与修正值的相对百分误差 |
| `REFERFLOWFIXED` |  | 辅流量修正值（l/min） |
| `REFERFLOWREFER` |  | 参考流量计指示的辅流量值（l/min） |
| `REFERFLOWTARGET` |  | 辅流量设定值（l/min）_（设定温度/流量显示屏） |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |

## RF_W_GASEOUSCHECK_CO
- 实体文件：`ReportForms/RF_W_GASEOUSCHECK_CO.cs`
- 视图：Views/ReportForms/RF_W_GASEOUSCHECK_CO.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `MPA` | 标气瓶压力 | 标气瓶压力(MPa) |
| `PPB` | 使用满量程 | 仪器编号： / 使用满量程（PPM） |
| `PPM` | 标气瓶浓度 | 标气瓶编号 / 标气瓶浓度（PPM） |
| `GHLM` | 更换滤膜 |  |
| `KDPY` | 跨度漂移(％) | 跨度漂移(％) |
| `AREAID` | 省市区 |  |
| `MCLPPM` | 满程量浓度 | 满量程的80％ |
| `REMARK` | 备注 | 备注： |
| `LDPYPPB` | 零点漂移(PPB) | 零点漂移(PPM) |
| `PPMCODE` | 标气瓶 | 标气瓶编号 / 标气瓶浓度（PPM） |
| `QYCKROW` | 气压导常记录 |  |
| `AGCCKROW` | AGC异常记录 |  |
| `BJREGION` | 背景范围 | 背景 |
| `ZYREGION` | 增益范围 | 增益 |
| `JXWDCKROW` | 机箱温度异常记录 |  |
| `PZDYCKROW` | 偏置电压异常记录 |  |
| `QYCKVALUE` | 气压 |  |
| `STATIONID` | 站点ID |  |
| `AGCCKVALUE` | AGC |  |
| `BJCHECKROW` | 背景导常记录 | 背景 |
| `CBCHECKROW` |  | 测量信号 (参比信号) / 1.17～1.22(API) 1.1～1.3(聚光) 20～90 mV(零气信号M)(大西比) 120～300 mV(标气信号M)(大西比) 2000～4900 mV（新先河） |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 | 仪器编号： / 使用满量程（PPM） |
| `FYCHECKROW` | 反应室温度导常记录 | 样品温度 / 48±4 ℃(API) 15～55 ℃(聚光) 8～47 ℃(赛默飞) 20～45 ℃(大西比) 48±1 ℃（新先河） |
| `GYCHECKROW` | 高压电源导常记录 | 测量信号 (测量电压) / 2500～4800 mV(API) 1～4 V(聚光) 2000～10000 mV(天虹) 300-3000 mV（新先河） |
| `JCQDLCKROW` | 检测器电流导常记录 |  |
| `JGCHECKROW` | 截距导常记录 | 截距(Offset) / 0±5 mV(API) -200～500(聚光) ＞-10.75 ppm(赛默飞) -5～5 ppm(天虹) -6.0～6.0 umol/mol(新先河) |
| `MCLEDTDATE` | 满程量结束时间 | 满量程的80％ |
| `MCLSDTDATE` | 满程量开始时间 | 满量程的80％ |
| `REVIEWDATE` | 复核时间 |  |
| `YLCHECKROW` | 斜率导常记录 | 斜率(Slope) / 1±0.3(API) 0.85～1.15(聚光) 0.500～2.000(赛默飞) 0.5～2(天虹) 0.7-1.3（新先河） |
| `ZYCHECKROW` | 增益导常记录 | 增益 |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEBRAND` |  | 仪器品牌： |
| `DEVICEMODEL` | 仪器型号 | 仪器型号： / 校准日期 |
| `GFCCHECKROW` | 相关轮温度异常记录 | 相关轮温度 ( GFC轮温度) / 68±2 ℃(API) 66～70 ℃(聚光) 44±1 ℃(大西比) 68±10 ℃（新先河） |
| `HWGYDLCKROW` | 红外光源电流导常记录 |  |
| `JXWDCKVALUE` | 机箱温度 |  |
| `LDSHOWVALUE` | 零点显示值 | 零点 |
| `LINGDIANPPM` | 零点浓度 | 零点 |
| `MCLHOWVALUE` | 满程量显示值 | 满量程的80％ |
| `PMTCHECKROW` | 参考PMT信号导常记录 | 参比信号 (参比电压) / 2500～4800 mV(API) 1～4 V(聚光) 2000～10000 mV(天虹) 5000～9000 mV(大西比) 300～3000 mV（新先河） |
| `PROCESSTYPE` | 处理方式 |  |
| `PZDYCKVALUE` | 偏置电压 |  |
| `ZWDCHECKROW` | 紫外灯光强导常记录 |  |
| `BJCHECKVALUE` | 背景检查值 | 背景 |
| `CBCHECKVALUE` |  | 测量信号 (参比信号) / 1.17～1.22(API) 1.1～1.3(聚光) 20～90 mV(零气信号M)(大西比) 120～300 mV(标气信号M)(大西比) 2000～4900 mV（新先河） |
| `CYLLCHECKROW` | 室采样流量导常记录 | 采样流量 (试样流量/样气) / 800±10% ml/min(API) 0.5～1.1 LPM(EC) 720～880 SCCM(聚光) 0.350～1.500 L/min(赛默飞) 300～1200 ml/min(天虹) 0.8～1.2 L/min(大西比) 1000±100 ml/min（新先河） |
| `CYYLCHECKROW` | 采样压力导常记录 | 采样压力 (样气压力) / 环境压力25～35 In-Hg-A(API) 430～800 TORR(EC) 7～15 PSIA(聚光) 250～1000 mmHg(赛默飞) 50～110 kPa(天虹) 79～106 kPa(大西比) 50-102 Kpa（新先河） |
| `DEFAULTVALUE` | 设置保存默认值 |  |
| `FYCHECKVALUE` | 反应室温度检查值 | 样品温度 / 48±4 ℃(API) 15～55 ℃(聚光) 8～47 ℃(赛默飞) 20～45 ℃(大西比) 48±1 ℃（新先河） |
| `GSWDCHECKROW` | 光室温度异常记录 | 光室温度 (光学室温度) / 48±2 ℃(API) 47～49 ℃(聚光) 380～500 mV(ESA) 40～52 ℃(赛默飞) 0～60 ℃(天虹) 40～45 ℃(大西比) 48±1 ℃（新先河） |
| `GYCHECKVALUE` | 高压电源检查值 | 测量信号 (测量电压) / 2500～4800 mV(API) 1～4 V(聚光) 2000～10000 mV(天虹) 300-3000 mV（新先河） |
| `JCQDLCKVALUE` | 检测器电流 |  |
| `JGCHECKVALUE` | 截距检查值 | 截距(Offset) / 0±5 mV(API) -200～500(聚光) ＞-10.75 ppm(赛默飞) -5～5 ppm(天虹) -6.0～6.0 umol/mol(新先河) |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `YLCHECKVALUE` | 斜率检查值 | 斜率(Slope) / 1±0.3(API) 0.85～1.15(聚光) 0.500～2.000(赛默飞) 0.5～2(天虹) 0.7-1.3（新先河） |
| `ZYCHECKVALUE` | 增益检查值 | 增益 |
| `AUDITORUSERID` | 审核人 |  |
| `CSCOCKXHCKROW` | 初始CO参考信号导常记录 |  |
| `GFCCHECKVALUE` | 相关轮温度检查值 | 相关轮温度 ( GFC轮温度) / 68±2 ℃(API) 66～70 ℃(聚光) 44±1 ℃(大西比) 68±10 ℃（新先河） |
| `HWGYDLCKVALUE` | 红外光源电流 |  |
| `PMTCHECKVALUE` | 参考PMT信号检查值 | 参比信号 (参比电压) / 2500～4800 mV(API) 1～4 V(聚光) 2000～10000 mV(天虹) 5000～9000 mV(大西比) 300～3000 mV（新先河） |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `ZWDCHECKVALUE` | 紫外灯光强检查值 |  |
| `CYLLCHECKVALUE` | 室采样流量检查值 | 采样流量 (试样流量/样气) / 800±10% ml/min(API) 0.5～1.1 LPM(EC) 720～880 SCCM(聚光) 0.350～1.500 L/min(赛默飞) 300～1200 ml/min(天虹) 0.8～1.2 L/min(大西比) 1000±100 ml/min（新先河） |
| `CYYLCHECKVALUE` | 采样压力检查值 | 采样压力 (样气压力) / 环境压力25～35 In-Hg-A(API) 430～800 TORR(EC) 7～15 PSIA(聚光) 250～1000 mmHg(赛默飞) 50～110 kPa(天虹) 79～106 kPa(大西比) 50-102 Kpa（新先河） |
| `GSWDCHECKVALUE` | 光室温度检查值 | 光室温度 (光学室温度) / 48±2 ℃(API) 47～49 ℃(聚光) 380～500 mV(ESA) 40～52 ℃(赛默飞) 0～60 ℃(天虹) 40～45 ℃(大西比) 48±1 ℃（新先河） |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 | 仪器型号： / 校准日期 |
| `CSCOCKXHCKVALUE` | 初始CO参考信号 |  |
| `LDBIAODINGVALUE` | 零点标定值 | 零点 |
| `LINGDIANEDTDATE` | 零点结束始时间 | 零点 |
| `LINGDIANSDTDATE` | 零点开始时间 | 零点 |
| `MCLBIAODINGVALUE` | 满程量标定值 | 满量程的80％ |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFWGASEOUSCHECKID` | id |  |

**平台校验器：**`BJCHECKVALUE`=required；`BJREGION`=required；`CBCHECKVALUE`=required；`CYLLCHECKVALUE`=required；`CYYLCHECKVALUE`=required；`DEVICEBRAND`=required；`DEVICECODE`=required；`DEVICEMODEL`=required；`FYCHECKVALUE`=required；`GFCCHECKVALUE`=required；`GSWDCHECKVALUE`=required；`GYCHECKVALUE`=required；`JGCHECKVALUE`=required；`LDBIAODINGVALUE`=required；`LINGDIANPPM`=required；`MCLBIAODINGVALUE`=required；`MCLPPM`=required；`MPA`=required；`PMTCHECKVALUE`=required；`PPB`=required；`PPM`=required；`PPMCODE`=required；`YLCHECKVALUE`=required；`ZYCHECKVALUE`=required；`ZYREGION`=required

## RF_W_GASEOUSCHECK_NOX
- 实体文件：`ReportForms/RF_W_GASEOUSCHECK_NOX.cs`
- 视图：Views/ReportForms/RF_W_GASEOUSCHECK_NOX.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `MPA` | 标气瓶压力 | 标气瓶压力(MPa) |
| `PPB` | 使用满量程 | 仪器编号： / 使用满量程（PPB） |
| `PPM` | 标气瓶浓度 | 标气瓶编号 / 标气瓶浓度（PPM） |
| `GHLM` | 更换滤膜 |  |
| `KDPY` | 跨度漂移(％) | 跨度漂移(％) |
| `AREAID` | 省市区 |  |
| `MCLPPM` | 满程量浓度 | 满量程的80％ |
| `REMARK` | 备注 | 备注： |
| `CYCKROW` | 臭氧流量异常记录 |  |
| `LDPYPPB` | 零点漂移(PPB) | 零点漂移(PPB) |
| `PPMCODE` | 标气瓶 | 标气瓶编号 / 标气瓶浓度（PPM） |
| `BJREGION` | 背景范围 | 背景 |
| `PTMCKROW` | PMT 温度异常记录 |  |
| `ZHLCKROW` | 转换炉异常记录 |  |
| `ZYREGION` | 增益范围 | 增益 |
| `CYCKVALUE` | 臭氧流量 |  |
| `HJYLCKROW` | 环境压力导常记录 |  |
| `HJYLVALUE` | 环境压力 |  |
| `JXWDCKROW` | 机箱温度异常记录 |  |
| `NOJJCKROW` | NO截距异常记录 |  |
| `NOXLCKROW` | NO斜率异常记录 |  |
| `STATIONID` | 站点ID |  |
| `BJCHECKROW` | 背景导常记录 | 背景 |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 | 仪器编号： / 使用满量程（PPB） |
| `FYCHECKROW` | 反应室温度导常记录 | 反应室温度 (测量室温度/试样槽温度) / 50±1 ℃(API) 47.0～53.0 ℃(EC) 50±1 ℃(聚光) 1350～1450 mV(ESA) 43±0.5 ℃(大西比) 48～52 ℃(赛默飞) 45～55 ℃(天虹) 50±1 ℃（新先河） |
| `FYCYLCKROW` | 反应室压力异常记录 |  |
| `GYCHECKROW` | 高压电源导常记录 | 高压电源 (光电倍增管高压) / 450～900 V(API) 640～700 V(EC) 450～900 v（聚光) 500～950 mV(ESA) -1200～0 V(赛默飞) -500～-1100 v(天虹) 500～900 V(大西比) |
| `JGCHECKROW` | 截距导常记录 |  |
| `MCLEDTDATE` | 满程量结束时间 | 满量程的80％ |
| `MCLSDTDATE` | 满程量开始时间 | 满量程的80％ |
| `NOXJJCKROW` | NOx截距异常记录 |  |
| `NOXXLCKROW` | NOx斜率异常记录 |  |
| `PTMCKVALUE` | PMT 温度 |  |
| `PTMDYCKROW` | PMT电压异常记录 |  |
| `REVIEWDATE` | 复核时间 |  |
| `YLCHECKROW` | 斜率导常记录 |  |
| `ZHLCKVALUE` | 转换炉 |  |
| `ZHLWDCKROW` | 转化炉温度导常记录 |  |
| `ZHLWDVALUE` | 转化炉温度 |  |
| `ZYCHECKROW` | 增益导常记录 | 增益 |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEBRAND` | 仪器品牌 | 仪器品牌： |
| `DEVICEMODEL` | 仪器型号 | 仪器型号： / 校准日期 |
| `JXWDCKVALUE` | 机箱温度 |  |
| `LDSHOWVALUE` | 零点显示值 | 零点 |
| `LINGDIANPPM` | 零点浓度 | 零点 |
| `MCLHOWVALUE` | 满程量显示值 | 满量程的80％ |
| `NOJJCKVALUE` | NO截距 |  |
| `NOXLCKVALUE` | NO斜率 |  |
| `PMTCHECKROW` | 参考PMT信号导常记录 | 参考PMT信号 (光电倍增管测量信号/模拟电压) / 0～5000 mv(API) 0-9999 mV(ESA) 1.5～4.096 v(聚光) -100-5000 mv（新先河） |
| `PROCESSTYPE` | 处理方式 |  |
| `ZHLCHECKROW` | 转化炉温度异常记录 | 转化炉温度 (转换炉) / 315±5 ℃(API) 315～335 ℃(EC) 305～350 ℃(聚光) 300～350 ℃(赛默飞) 180-360 ℃(天虹) 260～290 ℃(大西比) 315±5 ℃（新先河） |
| `ZWDCHECKROW` | 紫外灯光强导常记录 |  |
| `BJCHECKVALUE` | 背景检查值 | 背景 |
| `CYLLCHECKROW` | 室采样流量导常记录 | 采样流量 （试样流量/样气流量/总量) / 500±50 ml/min(API) 0.35～0.7 SLPM(EC) 350～650 sccm(聚光) 0.350～0.900 L/min(赛默飞) 300～800 ml/min(天虹) 0.15～0.5 L/min(大西比) 500±50 ml/min（新先河） |
| `CYYLCHECKROW` | 采样压力导常记录 | 采样压力 (样气压力/试样压力) / 环境压力25～30 In-Hg-A(API) 75～375 TORR(EC) 0～15 psia(聚光) 408～610 mV(ESA) 150～300 mmHg(赛默飞) 60～110 kpa(天虹) 8～40 kpa(大西比) 84～102 KPa(新先河) |
| `DEFAULTVALUE` | 设置保存默认值 |  |
| `FYCHECKVALUE` | 反应室温度检查值 | 反应室温度 (测量室温度/试样槽温度) / 50±1 ℃(API) 47.0～53.0 ℃(EC) 50±1 ℃(聚光) 1350～1450 mV(ESA) 43±0.5 ℃(大西比) 48～52 ℃(赛默飞) 45～55 ℃(天虹) 50±1 ℃（新先河） |
| `FYCYLCKVALUE` | 反应室压力 |  |
| `GYCHECKVALUE` | 高压电源检查值 | 高压电源 (光电倍增管高压) / 450～900 V(API) 640～700 V(EC) 450～900 v（聚光) 500～950 mV(ESA) -1200～0 V(赛默飞) -500～-1100 v(天虹) 500～900 V(大西比) |
| `JGCHECKVALUE` | 截距检查值 |  |
| `NOJGCHECKROW` | no截距导常记录 | NO截距 (Offset) / -50～150 mv (API) -20～50 ppb(聚光) >0(赛默飞) -50～50 ppb(天虹) -160 mv（先河） |
| `NOXJJCKVALUE` | NOx截距 |  |
| `NOXXLCKVALUE` | NOx斜率 |  |
| `NOYLCHECKROW` | no斜率导常记录 | NO斜率 (Slope) / 1±0.3(API) 0.85～1.15(聚光) 0.500～2.000(赛默飞) 0.5～2(天虹) 1±0.3（先河） |
| `PREPARERDATE` | 填报时间 |  |
| `PTMDYCKVALUE` | PMT电压 |  |
| `REVIEWUSERID` | 复核人 |  |
| `YLCHECKVALUE` | 斜率检查值 |  |
| `ZYCHECKVALUE` | 增益检查值 | 增益 |
| `AUDITORUSERID` | 审核人 |  |
| `FYSHICHECKROW` | 反应室压力异常记录 | 反应室压力 (测量室内部的真空压) / 0～15 psia(聚光) 133～433 mV(ESA) 13-34 KPa（新先河） |
| `NOXJGCHECKROW` | nox截距导常记录 | NOx截距 (Offset) / -10～150 mv(API) -20～50 ppb(聚光) >0(赛默飞) -50～50 ppb(天虹) -100～100 mv（新先河） |
| `NOXYLCHECKROW` | nox斜率导常记录 | NOx斜率 (Slope) / 1±0.3(API) 0.85～1.15(聚光) 0.500～2.000(赛默飞) 0.5～2(天虹) 1±0.3（新先河) |
| `PMTCHECKVALUE` | 参考PMT信号检查值 | 参考PMT信号 (光电倍增管测量信号/模拟电压) / 0～5000 mv(API) 0-9999 mV(ESA) 1.5～4.096 v(聚光) -100-5000 mv（新先河） |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `ZHLCHECKVALUE` | 转化炉温度 | 转化炉温度 (转换炉) / 315±5 ℃(API) 315～335 ℃(EC) 305～350 ℃(聚光) 300～350 ℃(赛默飞) 180-360 ℃(天虹) 260～290 ℃(大西比) 315±5 ℃（新先河） |
| `ZWDCHECKVALUE` | 紫外灯光强检查值 |  |
| `CYLLCHECKVALUE` | 室采样流量检查值 | 采样流量 （试样流量/样气流量/总量) / 500±50 ml/min(API) 0.35～0.7 SLPM(EC) 350～650 sccm(聚光) 0.350～0.900 L/min(赛默飞) 300～800 ml/min(天虹) 0.15～0.5 L/min(大西比) 500±50 ml/min（新先河） |
| `CYYLCHECKVALUE` | 采样压力检查值 | 采样压力 (样气压力/试样压力) / 环境压力25～30 In-Hg-A(API) 75～375 TORR(EC) 0～15 psia(聚光) 408～610 mV(ESA) 150～300 mmHg(赛默飞) 60～110 kpa(天虹) 8～40 kpa(大西比) 84～102 KPa(新先河) |
| `NOJGCHECKVALUE` | no截距检查值 | NO截距 (Offset) / -50～150 mv (API) -20～50 ppb(聚光) >0(赛默飞) -50～50 ppb(天虹) -160 mv（先河） |
| `NOYLCHECKVALUE` | no斜率检查值 | NO斜率 (Slope) / 1±0.3(API) 0.85～1.15(聚光) 0.500～2.000(赛默飞) 0.5～2(天虹) 1±0.3（先河） |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 | 仪器型号： / 校准日期 |
| `FYSHICHECKVALUE` | 反应室压力 | 反应室压力 (测量室内部的真空压) / 0～15 psia(聚光) 133～433 mV(ESA) 13-34 KPa（新先河） |
| `LDBIAODINGVALUE` | 零点标定值 | 零点 |
| `LINGDIANEDTDATE` | 零点结束始时间 | 零点 |
| `LINGDIANSDTDATE` | 零点开始时间 | 零点 |
| `NOXJGCHECKVALUE` | nox截距检查值 | NOx截距 (Offset) / -10～150 mv(API) -20～50 ppb(聚光) >0(赛默飞) -50～50 ppb(天虹) -100～100 mv（新先河） |
| `NOXYLCHECKVALUE` | nox斜率检查值 | NOx斜率 (Slope) / 1±0.3(API) 0.85～1.15(聚光) 0.500～2.000(赛默飞) 0.5～2(天虹) 1±0.3（新先河) |
| `CYLLIANGCHECKROW` | 臭氧流量异常记录 | 臭氧流量 (氧量) / 80±15 ml/min(API) 72～88 scc(聚光) >50 mL/min(赛默飞) 30～120 ml/min(天虹) 80±15 ml/min(新先河) 0.02～0.071 L/min（大西比） |
| `MCLBIAODINGVALUE` | 满程量标定值 | 满量程的80％ |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFWGASEOUSCHECKID` | id |  |
| `CYLLIANGCHECKVALUE` | 臭氧流量 | 臭氧流量 (氧量) / 80±15 ml/min(API) 72～88 scc(聚光) >50 mL/min(赛默飞) 30～120 ml/min(天虹) 80±15 ml/min(新先河) 0.02～0.071 L/min（大西比） |

**平台校验器：**`BJCHECKVALUE`=required；`BJREGION`=required；`CYLLCHECKVALUE`=required；`CYLLIANGCHECKVALUE`=required；`CYYLCHECKVALUE`=required；`DEVICEBRAND`=required；`DEVICECODE`=required；`DEVICEMODEL`=required；`FYCHECKVALUE`=required；`FYSHICHECKVALUE`=required；`GYCHECKVALUE`=required；`LDBIAODINGVALUE`=required；`LINGDIANPPM`=required；`MCLBIAODINGVALUE`=required；`MCLPPM`=required；`MPA`=required；`NOJGCHECKVALUE`=required；`NOXJGCHECKVALUE`=required；`NOXYLCHECKVALUE`=required；`NOYLCHECKVALUE`=required；`PMTCHECKVALUE`=required；`PPB`=required；`PPM`=required；`PPMCODE`=required；`ZHLCHECKVALUE`=required；`ZYCHECKVALUE`=required；`ZYREGION`=required

## RF_W_GASEOUSCHECK_O3
- 实体文件：`ReportForms/RF_W_GASEOUSCHECK_O3.cs`
- 视图：Views/ReportForms/RF_W_GaseousCheck_O3.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `MPA` | 标气瓶压力 |  |
| `PPB` | 使用满量程 | 仪器编号： / 使用满量程（PPB） |
| `PPM` | 标气瓶浓度 |  |
| `GHLM` | 更换滤膜 |  |
| `KDPY` | 跨度漂移(％) | 跨度漂移(％) |
| `AREAID` | 省市区 |  |
| `CDCODE` |  | 传递标准型号： / 传递时间 |
| `CDDATE` |  | 传递标准型号： / 传递时间 |
| `MCLPPM` | 满程量浓度 | 满量程的80％ |
| `REMARK` | 备注 | 备注： |
| `CDMODEL` |  | 传递标准编号： / 有效期 |
| `GQCKROW` | 光强异常记录 |  |
| `LDPYPPB` | 零点漂移(PPB) | 零点漂移(PPB) |
| `PPMCODE` | 标气瓶 |  |
| `YXQDATE` |  | 传递标准编号： / 有效期 |
| `BJREGION` | 背景范围 | 背景 |
| `DDLCKROW` | 灯电流导常记录 |  |
| `ZYREGION` | 增益范围 | 增益 |
| `CLXHCKROW` | 测量信号异常记录 |  |
| `GDCDCKROW` | 光池灯温度异常记录 |  |
| `JXWDCKROW` | 机箱温度异常记录 |  |
| `STATIONID` | 站点ID |  |
| `YPWDCKROW` | 样品温度异常记录 |  |
| `BJCHECKROW` | 背景导常记录 | 背景 |
| `CREATEDATE` | 创建日期 |  |
| `DDLCKVALUE` | 灯电流 |  |
| `DEVICECODE` | 仪器编号 | 仪器编号： / 使用满量程（PPB） |
| `FYCHECKROW` | 反应室温度导常记录 | 样品温度(光室内温度) / 10～50 ℃(API) 15～45 ℃(赛默飞) 30～70 ℃(天虹) 20～43 ℃(大西比) 0～55 ℃(新先河) |
| `GDJWDCKROW` | 光度计温度异常记录 |  |
| `GJZWDCKROW` | 光具座温度导常记录 |  |
| `GQCKVALUEA` | 光强A |  |
| `GQCKVALUEB` | 光强B |  |
| `GYCHECKROW` | 高压电源导常记录 | 测量信号(测量电压/紫外测量检测器信号) / 2500～4800 mV(API) 1.5～4.096 V(聚光) 500～4800 mV(ESA) 45000～150000 HZ(赛默飞) 2300～5200 mV(天虹) 2000～4900 mV(新先河) |
| `JGCHECKROW` | 截距导常记录 | 截距(Offset) / 0±5 ppb(API) -20～50 ppb(聚光) >-26.5(赛默飞) -50 ～ 50(天虹) -5～5 mv(新先河) |
| `MCLEDTDATE` | 满程量结束时间 | 满量程的80％ |
| `MCLSDTDATE` | 满程量开始时间 | 满量程的80％ |
| `REVIEWDATE` | 复核时间 |  |
| `YLCHECKROW` | 斜率导常记录 | 斜率(Slope) / 1.0±1.5(API) 0.85～1.15(聚光) 0.500～2.000(赛默飞) 0.5～2(天虹) 0.5～1.5(新先河) |
| `ZYCHECKROW` | 增益导常记录 | 增益 |
| `AUDITORDATE` | 审核时间 |  |
| `CLXHCKVALUE` | 测量信号 |  |
| `DEVICEBRAND` |  | 仪器品牌： |
| `DEVICEMODEL` | 仪器型号 | 仪器型号： / 校准日期 |
| `GDCDCKVALUE` | 光池灯温度 |  |
| `JXWDCKVALUE` | 机箱温度 |  |
| `LDSHOWVALUE` | 零点显示值 | 零点 |
| `LINGDIANPPM` | 零点浓度 | 零点 |
| `MCLHOWVALUE` | 满程量显示值 | 满量程的80％ |
| `PMTCHECKROW` | 参比信号导常记录 |  |
| `PROCESSTYPE` | 处理方式 |  |
| `YPWDCKVALUE` | 样品温度 |  |
| `ZWDCHECKROW` | 紫外灯光强导常记录 | 参比信号(参比电压/紫外参考检测器信号/模拟电压) / 2500～4800 mV(API) 1.5～4.096 V(聚光) 500～4800 mV(ESA) 45000～150000 HZ(赛默飞) 2300～5200 mV(天虹) 2000～4900 mV(新先河) |
| `BJCHECKVALUE` | 背景检查值 | 背景 |
| `CYLLCHECKROW` | 采样流量导常记录 | 采样流量(试样流量/样气流量) / 800±10% ml/min(API) 0.25～0.55 LPM(EC) 720～880 SCCM(聚光) 0.400～1.400 L/min(赛默飞A，B路) 300～1200 ml/min(天虹) 1.2～1.7 L/min(大西比) 800±80 ml/min(新先河) |
| `CYYLCHECKROW` | 采样压力导常记录 | 压力(样气压力) / 环境压力-2 In-Hg-A(API) 400～800 TORR(EC) 7～15 psia(聚光) 200～1000 mmHg(赛默飞) 50～110 kPa(天虹) 90～106 kPa(大西比) 50～102 kPa(新先河) |
| `DEFAULTVALUE` | 设置保存默认值 |  |
| `FYCHECKVALUE` | 反应室温度检查值 | 样品温度(光室内温度) / 10～50 ℃(API) 15～45 ℃(赛默飞) 30～70 ℃(天虹) 20～43 ℃(大西比) 0～55 ℃(新先河) |
| `GDJWDCKVALUE` | 光度计温度 |  |
| `GJZWDCKVALUE` | 光具座温度 |  |
| `GYCHECKVALUE` | 高压电源检查值 | 测量信号(测量电压/紫外测量检测器信号) / 2500～4800 mV(API) 1.5～4.096 V(聚光) 500～4800 mV(ESA) 45000～150000 HZ(赛默飞) 2300～5200 mV(天虹) 2000～4900 mV(新先河) |
| `JGCHECKVALUE` | 截距检查值 | 截距(Offset) / 0±5 ppb(API) -20～50 ppb(聚光) >-26.5(赛默飞) -50 ～ 50(天虹) -5～5 mv(新先河) |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `YLCHECKVALUE` | 斜率检查值 | 斜率(Slope) / 1.0±1.5(API) 0.85～1.15(聚光) 0.500～2.000(赛默飞) 0.5～2(天虹) 0.5～1.5(新先河) |
| `ZYCHECKVALUE` | 增益检查值 | 增益 |
| `AUDITORUSERID` | 审核人 |  |
| `GYBCHECKVALUE` |  | 测量信号(测量电压/紫外测量检测器信号) / 2500～4800 mV(API) 1.5～4.096 V(聚光) 500～4800 mV(ESA) 45000～150000 HZ(赛默飞) 2300～5200 mV(天虹) 2000～4900 mV(新先河) |
| `PMTCHECKVALUE` | 参比信号检查值 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `ZWDCHECKVALUE` | 紫外灯光强检查值 | 参比信号(参比电压/紫外参考检测器信号/模拟电压) / 2500～4800 mV(API) 1.5～4.096 V(聚光) 500～4800 mV(ESA) 45000～150000 HZ(赛默飞) 2300～5200 mV(天虹) 2000～4900 mV(新先河) |
| `CYLLCHECKVALUE` |  | 采样流量(试样流量/样气流量) / 800±10% ml/min(API) 0.25～0.55 LPM(EC) 720～880 SCCM(聚光) 0.400～1.400 L/min(赛默飞A，B路) 300～1200 ml/min(天虹) 1.2～1.7 L/min(大西比) 800±80 ml/min(新先河) |
| `CYYLCHECKVALUE` | 采样压力检查值 | 压力(样气压力) / 环境压力-2 In-Hg-A(API) 400～800 TORR(EC) 7～15 psia(聚光) 200～1000 mmHg(赛默飞) 50～110 kPa(天虹) 90～106 kPa(大西比) 50～102 kPa(新先河) |
| `PREPARERUSERID` | 填表人 |  |
| `ZWDBCHECKVALUE` |  | 参比信号(参比电压/紫外参考检测器信号/模拟电压) / 2500～4800 mV(API) 1.5～4.096 V(聚光) 500～4800 mV(ESA) 45000～150000 HZ(赛默飞) 2300～5200 mV(天虹) 2000～4900 mV(新先河) |
| `CALIBRATIONDATE` | 校准日期 | 仪器型号： / 校准日期 |
| `CYLLBCHECKVALUE` |  | 采样流量(试样流量/样气流量) / 800±10% ml/min(API) 0.25～0.55 LPM(EC) 720～880 SCCM(聚光) 0.400～1.400 L/min(赛默飞A，B路) 300～1200 ml/min(天虹) 1.2～1.7 L/min(大西比) 800±80 ml/min(新先河) |
| `CYLLCHECKVALUEA` | 采样流量检查值A |  |
| `CYLLCHECKVALUEB` | 采样流量检查值B |  |
| `LDBIAODINGVALUE` | 零点标定值 | 零点 |
| `LINGDIANEDTDATE` | 零点结束始时间 | 零点 |
| `LINGDIANSDTDATE` | 零点开始时间 | 零点 |
| `MCLBIAODINGVALUE` | 满程量标定值 | 满量程的80％ |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFWGASEOUSCHECKID` | id |  |

**平台校验器：**`BJCHECKVALUE`=required；`BJREGION`=required；`CDCODE`=required；`CDMODEL`=required；`CYLLBCHECKVALUE`=required；`CYLLCHECKVALUE`=required；`CYYLCHECKVALUE`=required；`DEVICEBRAND`=required；`DEVICECODE`=required；`DEVICEMODEL`=required；`FYCHECKVALUE`=required；`GYBCHECKVALUE`=required；`GYCHECKVALUE`=required；`JGCHECKVALUE`=required；`LDBIAODINGVALUE`=required；`LINGDIANPPM`=required；`MCLBIAODINGVALUE`=required；`MCLPPM`=required；`PPB`=required；`YLCHECKVALUE`=required；`ZWDBCHECKVALUE`=required；`ZWDCHECKVALUE`=required；`ZYCHECKVALUE`=required；`ZYREGION`=required

## RF_W_GASEOUSCHECK_SO2
- 实体文件：`ReportForms/RF_W_GASEOUSCHECK_SO2.cs`
- 视图：Views/ReportForms/RF_W_GaseousCheck_SO2.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `MPA` | 标气瓶压力 | 标气瓶压力(MPa) |
| `PPB` | 使用满量程 | 仪器编号： / 使用满量程（PPB） |
| `PPM` | 标气瓶浓度 | 标气瓶编号 / 标气瓶浓度（PPM） |
| `GHLM` | 更换滤膜 |  |
| `KDPY` | 跨度漂移(％) | 跨度漂移(％) |
| `AREAID` | 省市区 |  |
| `MCLPPM` | 满程量浓度 | 满量程的80％ |
| `REMARK` | 备注 | 备注： |
| `LDPYPPB` | 零点漂移(PPB) | 零点漂移(PPB) |
| `PPMCODE` | 标气瓶 | 标气瓶编号 / 标气瓶浓度（PPM） |
| `BJREGION` | 背景范围 | 背景 |
| `GYGCKROW` | 干扰光异常记录 |  |
| `PTMCKROW` | PMT 温度异常记录 |  |
| `ZYREGION` | 增益范围 | 增益 |
| `DBJZCKROW` | 灯背景值异常记录 |  |
| `JXWDCKROW` | 机箱温度异常记录 |  |
| `STATIONID` | 站点ID |  |
| `BJCHECKROW` | PMT背景导常记录 | 背景 |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 | 仪器编号： / 使用满量程（PPB） |
| `FYCHECKROW` | 反应室温度导常记录 | 反应室温度 / 50±1℃（API） 50±5℃（聚光/天虹） 43～47℃（赛默飞） 32℃～45℃（Dasibi） 50±3℃（EC) 50±1℃（新先河） |
| `GYCHECKROW` | 高压电源导常记录 | 高压电源 (倍增管高压/高压) / 400～900 V（API） 400～900 V（聚光） -500～-1200 V （赛默飞） 630～730 V（EC） -500～-1100 V（天虹） 600～900（大西比） 450～900 v（新先河） |
| `GYGCKVALUE` | 干扰光 |  |
| `JGCHECKROW` | 截距导常记录 | 截距 / -20～50 ppb（聚光) > 0（赛默飞） -50～50 ppb（天虹) |
| `MCLEDTDATE` | 满程量结束时间 | 满量程的80％ |
| `MCLSDTDATE` | 满程量开始时间 | 满量程的80％ |
| `PTMCKVALUE` | PMT 温度 |  |
| `PTMDYCKROW` | PMT电压异常记录 |  |
| `REVIEWDATE` | 复核时间 |  |
| `YLCHECKROW` | 斜率导常记录 | 斜率 / 1±0.3（API） 0.85～1.15（聚光） 0.500～2.000（赛默飞） 0.4-2（天虹) 0.1～0.3（新先河） |
| `ZWDDLCKROW` | 紫外灯电流异常记录 |  |
| `ZWDDYCKROW` | 紫外灯电压异常记录 |  |
| `ZYCHECKROW` | 增益导常记录 | 增益 |
| `AUDITORDATE` | 审核时间 |  |
| `DBJZCKVALUE` | 灯背景值 |  |
| `DEVICEBRAND` | 仪器品牌 | 仪器品牌： |
| `DEVICEMODEL` | 仪器型号 | 仪器型号： / 校准日期 |
| `JXWDCKVALUE` | 机箱温度 |  |
| `LDSHOWVALUE` | 零点显示值 | 零点 |
| `LINGDIANPPM` | 零点浓度 | 零点 |
| `MCLHOWVALUE` | 满程量显示值 | 满量程的80％ |
| `PMTCHECKROW` | 参考PMT信号导常记录 | 参考PMT信号 (或模拟电/ PMT通零状态） / 0～5000 mv（API） 1.5～4.096 v（聚光） 11.6～12.2 v（EC） 0～5000 mv（新先河） 0～200 mv（大西比） |
| `PROCESSTYPE` | 处理方式 |  |
| `ZWDCHECKROW` | 紫外灯光强导常记录 | 紫外灯光强 （紫外灯参比电压/紫外灯信号/锌灯电压/光强） / 700～4000 mv（API） 1.5～4.096 v（聚光） 40～100%（赛默飞） 300-5000 mv（天虹） 3.5～9.0 v（Dasibi） 1.50～3.50 v（EC） 2.0～9.0 v（ESA） |
| `BJCHECKVALUE` | PMT背景检查值 | 背景 |
| `CYLLCHECKROW` | 室采样流量导常记录 | 室采样流量 (样气流量) / 650±10% ml/min（API） 300～800 ml/min（天虹） 0.5～0.8 L/min（Dasibi） 580～720 sccm（聚光） 0.350～0.750 L/min (赛默飞) 0.4～0.8 SLPM（EC） 650±65ml/min(新先河) |
| `CYYLCHECKROW` | 采样压力导常记录 | 采样压力 （样气压力） / 环境压力±2In-Hg-A（API） 7～15 PSIA（聚光） 400～1000 mmHg (赛默飞) 50～105 kpa（天虹） 13～79 kpa(大西比) 400-800 TORR（EC） 50-102 kpa（新先河） |
| `DEFAULTVALUE` | 设置保存默认值 |  |
| `FYCHECKVALUE` | 反应室温度检查值 | 反应室温度 / 50±1℃（API） 50±5℃（聚光/天虹） 43～47℃（赛默飞） 32℃～45℃（Dasibi） 50±3℃（EC) 50±1℃（新先河） |
| `GYCHECKVALUE` | 高压电源检查值 | 高压电源 (倍增管高压/高压) / 400～900 V（API） 400～900 V（聚光） -500～-1200 V （赛默飞） 630～730 V（EC） -500～-1100 V（天虹） 600～900（大西比） 450～900 v（新先河） |
| `JGCHECKVALUE` | 截距检查值 | 截距 / -20～50 ppb（聚光) > 0（赛默飞） -50～50 ppb（天虹) |
| `PREPARERDATE` | 填报时间 |  |
| `PTMDYCKVALUE` | PMT电压 |  |
| `REVIEWUSERID` | 复核人 |  |
| `YLCHECKVALUE` | 斜率检查值 | 斜率 / 1±0.3（API） 0.85～1.15（聚光） 0.500～2.000（赛默飞） 0.4-2（天虹) 0.1～0.3（新先河） |
| `ZWDDLCKVALUE` | 紫外灯电流 |  |
| `ZWDDYCKVALUE` | 紫外灯电压 |  |
| `ZYCHECKVALUE` | 增益检查值 | 增益 |
| `AUDITORUSERID` | 审核人 |  |
| `PMTCHECKVALUE` | 参考PMT信号检查值 | 参考PMT信号 (或模拟电/ PMT通零状态） / 0～5000 mv（API） 1.5～4.096 v（聚光） 11.6～12.2 v（EC） 0～5000 mv（新先河） 0～200 mv（大西比） |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `ZWDCHECKVALUE` | 紫外灯光强检查值 | 紫外灯光强 （紫外灯参比电压/紫外灯信号/锌灯电压/光强） / 700～4000 mv（API） 1.5～4.096 v（聚光） 40～100%（赛默飞） 300-5000 mv（天虹） 3.5～9.0 v（Dasibi） 1.50～3.50 v（EC） 2.0～9.0 v（ESA） |
| `CYLLCHECKVALUE` | 室采样流量检查值 | 室采样流量 (样气流量) / 650±10% ml/min（API） 300～800 ml/min（天虹） 0.5～0.8 L/min（Dasibi） 580～720 sccm（聚光） 0.350～0.750 L/min (赛默飞) 0.4～0.8 SLPM（EC） 650±65ml/min(新先河) |
| `CYYLCHECKVALUE` | 采样压力检查值 | 采样压力 （样气压力） / 环境压力±2In-Hg-A（API） 7～15 PSIA（聚光） 400～1000 mmHg (赛默飞) 50～105 kpa（天虹） 13～79 kpa(大西比) 400-800 TORR（EC） 50-102 kpa（新先河） |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 | 仪器型号： / 校准日期 |
| `LDBIAODINGVALUE` | 零点标定值 | 零点 |
| `LINGDIANEDTDATE` | 零点结束始时间 | 零点 |
| `LINGDIANSDTDATE` | 零点开始时间 | 零点 |
| `MCLBIAODINGVALUE` | 满程量标定值 | 满量程的80％ |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `RFWGASEOUSCHECKID` | id |  |

**平台校验器：**`BJCHECKVALUE`=required；`BJREGION`=required；`CYLLCHECKVALUE`=required；`CYYLCHECKVALUE`=required；`DEVICEBRAND`=required；`DEVICECODE`=required；`DEVICEMODEL`=required；`FYCHECKVALUE`=required；`GYCHECKVALUE`=required；`JGCHECKVALUE`=required；`LDBIAODINGVALUE`=required；`LINGDIANPPM`=required；`MCLBIAODINGVALUE`=required；`MCLPPM`=required；`MPA`=required；`PMTCHECKVALUE`=required；`PPB`=required；`PPM`=required；`PPMCODE`=required；`YLCHECKVALUE`=required；`ZWDCHECKVALUE`=required；`ZYCHECKVALUE`=required；`ZYREGION`=required

## RF_W_GrainCalibrationCheckAttach
- 实体文件：`ReportForms/RF_W_GrainCalibrationCheck.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `XDWC` | 相对误差1 |  |
| `LLJXH` | 流量计 型 号1 |  |
| `SYCJCZ` | 上一次监测值1 |  |
| `XYCJCZ` | 下一次监测值1 |  |
| `LLJCCBH` | 流量计 出厂编号1 |  |
| `FORMTYPE` | 工单编号加表单类型 |  |
| `POLLUTANT` | 监测项目1 |  |
| `WORKINGORDERCODE` | 工单编号加表单类型 |  |

## RF_W_GrainCalibrationCheck_PM10
- 实体文件：`ReportForms/RF_W_GrainCalibrationCheck.cs`
- 视图：Views/ReportForms/RF_W_GrainCalibrationCheck_PM10.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `NEW` | NEW | Z ERO FOIL / D 1 |
| `OLD` | OLD | Z ERO FOIL / D 1 |
| `BZZ1` | 校准值（Vc）1 | Z ERO FOIL / D 1 |
| `BZZ2` | 校准值（Vc）2 | S P A N FOIL / D 2 |
| `CCCJ` | 生产厂家 |  |
| `CZSJ` | 操作日期 | 操作日期： / 开始时间： / 结束时间： |
| `EDZ1` | 额定值（Vs）1 | Z ERO FOIL / D 1 |
| `EDZ2` | 额定值（Vs）2 | S P A N FOIL / D 2 |
| `JSSJ` | 结束时间 | 操作日期： / 开始时间： / 结束时间： |
| `KSSJ` | 开始时间 | 操作日期： / 开始时间： / 结束时间： |
| `SNSD` | 室内湿度 | 室内温度： / 室内湿度： |
| `SNWD` | 室内温度 | 室内温度： / 室内湿度： |
| `D1WC1` | D1相对 误差1 | Z ERO FOIL / D 1 |
| `D2WC2` | D2相对 误差2 | S P A N FOIL / D 2 |
| `XSJZH` | 系数校准后 |  |
| `XSJZQ` | 系数校准前 |  |
| `AREAID` |  |  |
| `REMARK` |  | 备注： |
| `BJZCCBH` | 标准膜出厂编号 |  |
| `BZMMODEL` | 标准膜型号 |  |
| `CHECKDATE` |  |  |
| `STATIONID` |  |  |
| `CREATEDATE` |  |  |
| `REVIEWDATE` |  |  |
| `AUDITORDATE` |  |  |
| `PROCESSTYPE` |  |  |
| `PREPARERDATE` |  |  |
| `REVIEWUSERID` |  |  |
| `AUDITORUSERID` |  |  |
| `POLLUTANTTYPE` |  |  |
| `PREPARERUSERID` |  |  |
| `OPERATIONSUNITID` |  |  |
| `WORKINGORDERCODE` |  |  |
| `GRAINCALIBRATIONCHECKID` |  |  |

**平台校验器：**`BJZCCBH`=required；`BZMMODEL`=required；`BZZ1`=required；`BZZ2`=required；`CCCJ`=required；`D1WC1`=required；`D2WC2`=required；`EDZ1`=required；`EDZ2`=required；`NEW`=required；`OLD`=required；`SNSD`=required；`SNWD`=required；`XSJZH`=required；`XSJZQ`=required

## RF_W_GrainCalibrationCheck_PM25
- 实体文件：`ReportForms/RF_W_GrainCalibrationCheck.cs`
- 视图：Views/ReportForms/RF_W_GrainCalibrationCheck_PM25.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `NEW` | NEW | Z ERO FOIL / D 1 |
| `OLD` | OLD | Z ERO FOIL / D 1 |
| `BZZ1` | 校准值（Vc）1 | Z ERO FOIL / D 1 |
| `BZZ2` | 校准值（Vc）2 | S P A N FOIL / D 2 |
| `CCCJ` | 生产厂家 |  |
| `CZSJ` | 操作日期 | 操作日期： / 开始时间： / 结束时间： |
| `EDZ1` | 额定值（Vs）1 | Z ERO FOIL / D 1 |
| `EDZ2` | 额定值（Vs）2 | S P A N FOIL / D 2 |
| `JSSJ` | 结束时间 | 操作日期： / 开始时间： / 结束时间： |
| `KSSJ` | 开始时间 | 操作日期： / 开始时间： / 结束时间： |
| `SNSD` | 室内湿度 | 室内温度： / 室内湿度： |
| `SNWD` | 室内温度 | 室内温度： / 室内湿度： |
| `D1WC1` | D1相对 误差1 | Z ERO FOIL / D 1 |
| `D2WC2` | D2相对 误差2 | S P A N FOIL / D 2 |
| `XSJZH` | 系数校准后 |  |
| `XSJZQ` | 系数校准前 |  |
| `AREAID` |  |  |
| `REMARK` |  | 备注： |
| `BJZCCBH` | 标准膜出厂编号 |  |
| `BZMMODEL` | 标准膜型号 |  |
| `CHECKDATE` |  |  |
| `STATIONID` |  |  |
| `CREATEDATE` |  |  |
| `REVIEWDATE` |  |  |
| `AUDITORDATE` |  |  |
| `PROCESSTYPE` |  |  |
| `PREPARERDATE` |  |  |
| `REVIEWUSERID` |  |  |
| `AUDITORUSERID` |  |  |
| `POLLUTANTTYPE` |  |  |
| `PREPARERUSERID` |  |  |
| `OPERATIONSUNITID` |  |  |
| `WORKINGORDERCODE` |  |  |
| `GRAINCALIBRATIONCHECKID` |  |  |

**平台校验器：**`BJZCCBH`=required；`BZMMODEL`=required；`BZZ1`=required；`BZZ2`=required；`CCCJ`=required；`D1WC1`=required；`D2WC2`=required；`EDZ1`=required；`EDZ2`=required；`NEW`=required；`OLD`=required；`SNSD`=required；`SNWD`=required；`XSJZH`=required；`XSJZQ`=required

## RF_W_INSPECTION
- 实体文件：`ReportForms/RF_W_Inspection.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `ENDTIME` |  |  |
| `INSIDE1` | 站房内部的供电、通讯是否畅通 |  |
| `INSIDE2` | 站房内部给排水、供暖设施、空调工作状况 |  |
| `INSIDE3` | 站房内有无气泵产生的异常声音 |  |
| `INSIDE4` | 站房内有无异常气味 |  |
| `INSIDE5` | 站房温度、湿度是否符合要求 |  |
| `INSIDE6` | 气体采样总管采样风扇工作是否正常 |  |
| `INSIDE7` | 气体采样总管及支管是否由于室外温差产生冷凝水 |  |
| `INSIDE8` | 站房排风扇是否正常运行 |  |
| `INSIDE9` | 稳压电源参数是否正常 |  |
| `INSIDE10` | 各电源插头、线板工作是否正常 |  |
| `INSIDE11` | 检查颗粒物采样头、清理雨水瓶积水 |  |
| `INSIDE12` | 仪器气泵工作是否正常 |  |
| `INSIDE13` | 检查/更换干燥剂，蓝色剩1/3～1/4 时及时更换 |  |
| `INSIDE14` | 检查钢瓶气减压阀压力指示情况 |  |
| `INSIDE15` | 检查颗粒物分析仪纸带位置是否正常，如长度不足时应提前更换 |  |
| `INSIDE16` | 检查振荡天平法仪器气水分离器是否有积水，必要时进行清理 |  |
| `OUTSIDE1` | 点位周围环境变化情况 |  |
| `OUTSIDE2` | 点位周围安全隐患 |  |
| `OUTSIDE3` | 点位周围道路、供电线路、通讯线路、给排水设施完好或损坏状况 |  |
| `OUTSIDE4` | 站房外围的防护栏、隔离带有无损坏情况 |  |
| `OUTSIDE5` | 视频监控系统是否正常 |  |
| `OUTSIDE6` | 周围树木是否需要修剪 |  |
| `OUTSIDE7` | 站房防雷接地是否完好 |  |
| `OUTSIDE8` | 站房屋顶是否完好，有无漏雨 |  |
| `CHECKDATE` | 检查时间 |  |
| `STARTTIME` |  |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `DEFAULTVALUE` | 设置保存默认值 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `RFWINSPECTIONID` | 流水号 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |

## RF_W_INSPECTIONSUMMARY
- 实体文件：`ReportForms/RF_W_INSPECTIONSUMMARY.cs`
- 视图：Views/ReportForms/RF_W_InspectionSummary.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `CAR` | 车辆 | 车辆 |
| `OTHER` | 其他需要记录的内容 | 其他需要记录的内容 |
| `USERS` | 人员 | 人员 |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `CHECKDATE` | 检查时间 |  |
| `PATROLMAN` | 巡检人 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `DEFAULTVALUE` | 设置保存默认值 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `CHANGEMACHINE` | 更换备机类 | 更换备机类 |
| `STATIONINTIME` | 进站房时间 | 巡检人 / 进站房时间 |
| `PREPARERUSERID` | 填表人 |  |
| `STATIONOUTTIME` | 出站房时间 | 出站房时间 |
| `CALIBRATIONCLASS` | 仪器检查校准类 | 仪器检查校准类 |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `ROUTINEINSPECTION` | 常规巡检 | 常规巡检 |
| `CLEANINGMAINTENANCE` | 清洗维护类 | 清洗维护类 |
| `EQUIPMENTMAINTENANCE` | 设备维修类 | 设备维修类 |
| `REPLACEMENTSPAREPARTS` | 更换耗材备件类 | 更换耗材备件类 |
| `RFWINSPECTIONSUMMARYID` |  |  |

**平台校验器：**`CALIBRATIONCLASS`=required；`CAR`=required；`CHANGEMACHINE`=required；`CLEANINGMAINTENANCE`=required；`EQUIPMENTMAINTENANCE`=required；`OTHER`=required；`REPLACEMENTSPAREPARTS`=required；`ROUTINEINSPECTION`=required；`USERS`=required

## RF_W_LONGOPTICALPATH
- 实体文件：`ReportForms/RF_W_LONGOPTICALPATH.cs`
- 视图：Views/ReportForms/RF_W_LongOpticalPath.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 | 备注： |
| `CHECKDATE` | 检查时间 |  |
| `ENDTIMEO3` | O3结束时间 | O3 / , Model.STARTTIMEO3 , true , "yyyy-MM-dd HH:mm", "ENDTIMEO3", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMEO3 , true , "yyyy-MM-dd HH:mm", "STARTTIMEO3", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 | 仪器编号： |
| `ENDTIMENO2` | NO2结束时间 | NO2 / , Model.STARTTIMENO2 , true , "yyyy-MM-dd HH:mm", "ENDTIMENO2", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMENO2 , true , "yyyy-MM-dd HH:mm", "STARTTIMENO2", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `ENDTIMESO2` | SO2结束时间 | 蓝盾设备零点校准 / SO2 / , Model.STARTTIMESO2 , true , "yyyy-MM-dd HH:mm", "ENDTIMESO2", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMESO2 , true , "yyyy-MM-dd HH:mm", "STARTTIMESO2", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `ISLDDEVICE` | 是否蓝盾设备 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 仪器型号 | 仪器型号： / 校准日期： |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `STARTTIMEO3` | O3开始时间 | O3 / , Model.STARTTIMEO3 , true , "yyyy-MM-dd HH:mm", "ENDTIMEO3", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMEO3 , true , "yyyy-MM-dd HH:mm", "STARTTIMEO3", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `DEFAULTVALUE` | 设置保存默认值 |  |
| `GRATINGCHECK` | 光栅定位的准确性是否通过 | 光栅定位的准确性 |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `STARTTIMENO2` | NO2开始时间 | NO2 / , Model.STARTTIMENO2 , true , "yyyy-MM-dd HH:mm", "ENDTIMENO2", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMENO2 , true , "yyyy-MM-dd HH:mm", "STARTTIMENO2", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `STARTTIMESO2` | SO2开始时间 | 蓝盾设备零点校准 / SO2 / , Model.STARTTIMESO2 , true , "yyyy-MM-dd HH:mm", "ENDTIMESO2", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMESO2 , true , "yyyy-MM-dd HH:mm", "STARTTIMESO2", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `AUDITORUSERID` | 审核人 |  |
| `SPECTRUMCHECK` | 光谱采样的稳定性是否通过 | 光谱采样的稳定性 |
| `DISPLAYVALUEO3` | O3显示值 | O3 / , Model.STARTTIMEO3 , true , "yyyy-MM-dd HH:mm", "ENDTIMEO3", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMEO3 , true , "yyyy-MM-dd HH:mm", "STARTTIMEO3", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 | 仪器型号： / 校准日期： |
| `DISPLAYVALUENO2` | NO2显示值 | NO2 / , Model.STARTTIMENO2 , true , "yyyy-MM-dd HH:mm", "ENDTIMENO2", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMENO2 , true , "yyyy-MM-dd HH:mm", "STARTTIMENO2", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `DISPLAYVALUESO2` | SO2显示值 | 蓝盾设备零点校准 / SO2 / , Model.STARTTIMESO2 , true , "yyyy-MM-dd HH:mm", "ENDTIMESO2", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMESO2 , true , "yyyy-MM-dd HH:mm", "STARTTIMESO2", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `GRATINGSITUATION` | 光栅定位的准确性异常时处理记录 | 光栅定位的准确性 |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `SPECTRUMSITUATION` | 光谱采样的稳定性异常时处理记录 | 光谱采样的稳定性 |
| `CALIBRATIONVALUEO3` | O3标定值 | O3 / , Model.STARTTIMEO3 , true , "yyyy-MM-dd HH:mm", "ENDTIMEO3", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMEO3 , true , "yyyy-MM-dd HH:mm", "STARTTIMEO3", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `CALIBRATIONVALUENO2` | NO2标定值 | NO2 / , Model.STARTTIMENO2 , true , "yyyy-MM-dd HH:mm", "ENDTIMENO2", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMENO2 , true , "yyyy-MM-dd HH:mm", "STARTTIMENO2", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `CALIBRATIONVALUESO2` | SO2标定值 | 蓝盾设备零点校准 / SO2 / , Model.STARTTIMESO2 , true , "yyyy-MM-dd HH:mm", "ENDTIMESO2", false , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked" ) / , Model.ENDTIMESO2 , true , "yyyy-MM-dd HH:mm", "STARTTIMESO2", true , minDate: DateTime.Now.AddDays(-1).ToString() , maxDate: DateTime.Now.AddDays(1).ToString() , onpicked: "onpicked") |
| `LIGHTINTENSITYVALUE` | 光路光强(外光光强）检查值 | 光路光强(外光光强） / &gt;30000 |
| `RFWLONGOPTICALPATHID` | 流水号 |  |
| `LIGHTINTENSITYSITUATION` | 光路光强(外光光强）异常时处理记录 | 光路光强(外光光强） / &gt;30000 |

**平台校验器：**`DEVICECODE`=required；`DEVICEMODEL`=required；`GRATINGCHECK`=required；`LIGHTINTENSITYVALUE`=required；`SPECTRUMCHECK`=required

## RF_W_OTHERDEVICECHECK
- 实体文件：`ReportForms/RF_W_OtherDeviceCheck.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ISOK1` |  |  |
| `ISOK2` |  |  |
| `ISOK3` |  |  |
| `ISOK4` |  |  |
| `AREAID` | 省市区 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `DEFAULTVALUE` | 设置保存默认值 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WEATHERSITUATION` | 气象五参数运行状况及处置情况 |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `WEATHERDEVICEMODEL` | 气象五参数仪器型号 |  |
| `CITYCAMERASITUATION` | 城市摄影系统运行状况及处置情况 |  |
| `VISIBILITYSITUATION` | 能见度仪器运行状况及处置情况 |  |
| `CITYCAMERADEVICEMODEL` | 城市摄影系统仪器型号 |  |
| `RFWOTHERDEVICECHECKID` | 流水号 |  |
| `VISIBILITYDEVICEMODEL` | 能见度仪器型号 |  |
| `DATAACQUISITIONSITUATION` | 数采系统软硬件运行状况及处置情况 |  |
| `DATAACQUISITIONDEVICEMODEL` | 数采系统软硬件仪器型号 |  |

## RF_W_PmCheck
- 实体文件：`ReportForms/RF_W_PmCheck.cs`

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `OTHERVALUE` | 其他参数 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEBRAND` |  |  |
| `DEVICECODEN` | 仪器编号 |  |
| `DEVICEMODEL` | 仪器型号 |  |
| `PROCESSTYPE` | 处理方式（1：现场维修/调试，2：更换备机，3：其他） |  |
| `AIRTEMPVALUE` | 采样管温度检查值 |  |
| `DEFAULTVALUE` | 设置保存默认值 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `RFWPMCHECKID` | 流水号 |  |
| `AUDITORUSERID` | 审核人 |  |
| `CHECKISNORMAL` | 检查PM2.5、PM10分析仪相对湿度、温度传感器、压力和动态加热装置是否正常 |  |
| `MAINFLOWVALUE` | 流量检查值 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `PREPARERUSERID` | 填表人 |  |
| `AIRTEMPISNORMAL` | 采样管温度是否正常 |  |
| `AIRTEMPEXCEPTION` | 采样管温度异常时处理记录 |  |
| `MAINFLOWISNORMAL` | 流量是否正常 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `MAINFLOWEXCEPTION` | 流量异常时处理记录 |  |
| `TAPEUSAGEDISPOSAL` | 纸带使用量及处置情况 |  |
| `TEOMMEMBRANEDISPOSAL` | TEOM滤膜负载及处置情况 |  |

## RF_W_STANDARD_ALL
- 实体文件：`SEC/RF_W_STANDARD_ALL.cs`
- 视图：Views/ReportForms/RF_W_Standard_ALL.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `CHECKDATE` | 检查时间 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICECODE` | 仪器编号 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间 |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` | 污染物类型 |  |
| `DEVICEMODEL_CO` | 型号CO | 一氧化碳分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEMODEL_DT` | 型号DT | 动态气体校准仪 / &nbsp; |
| `DEVICEMODEL_LJ` | 型号LJ | 零气发生器 / &nbsp; |
| `DEVICEMODEL_O3` | 型号O3 | 臭氧分析仪 / 与仪器显示流量误差在10%范围内 |
| `PREPARERUSERID` | 填表人 |  |
| `CALIBRATIONDATE` | 校准日期 |  |
| `DEVICEMODEL_NO2` | 型号NO2 | 氮氧化物分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEMODEL_SO2` | 型号SO2 | 二氧化硫分析仪 / 与仪器显示流量误差在10%范围内 |
| `RFSTANDARDALLID` | id |  |
| `DEVICEBZVALUE_CO` | 标准值CO | 一氧化碳分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEBZVALUE_DT` | 标准值DT | 动态气体校准仪 / &nbsp; |
| `DEVICEBZVALUE_LJ` | 标准值LJ | 零气发生器 / &nbsp; |
| `DEVICEBZVALUE_O3` | 标准值O3 | 臭氧分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEJCVALUE_CO` | 监测值CO | 一氧化碳分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEJCVALUE_DT` | 监测值DT | 动态气体校准仪 / &nbsp; |
| `DEVICEJCVALUE_LJ` | 监测值LJ | 零气发生器 / &nbsp; |
| `DEVICEJCVALUE_O3` | 监测值O3 | 臭氧分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEMODEL_PM10` | 型号PM10 | 颗粒物在线分析仪 / 16.7L/min,与仪器标准流量误差在5%范围内 |
| `DEVICEMODEL_PM25` | 型号PM25 | 颗粒物在线分析仪 PM25 / 16.7L/min,与仪器标准流量误差在5%范围内 |
| `DEVICEWCVALUE_CO` | 误差CO | 一氧化碳分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEWCVALUE_DT` | 误差DT | 动态气体校准仪 / &nbsp; |
| `DEVICEWCVALUE_LJ` | 误差LJ | 零气发生器 / &nbsp; |
| `DEVICEWCVALUE_O3` | 误差O3 | 臭氧分析仪 / 与仪器显示流量误差在10%范围内 |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单编号 |  |
| `DEVICEBZVALUE_NO2` | 标准值NO2 | 氮氧化物分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEBZVALUE_SO2` | 标准值SO2 | 二氧化硫分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEJCVALUE_NO2` | 监测值NO2 | 氮氧化物分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEJCVALUE_SO2` | 监测值SO2 | 二氧化硫分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEWCVALUE_NO2` | 误差NO2 | 氮氧化物分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEWCVALUE_SO2` | 误差SO2 | 二氧化硫分析仪 / 与仪器显示流量误差在10%范围内 |
| `DEVICEBZVALUE_PM10` | 标准值PM10 | 颗粒物在线分析仪 / 16.7L/min,与仪器标准流量误差在5%范围内 |
| `DEVICEBZVALUE_PM25` | 标准值PM25 | 颗粒物在线分析仪 PM25 / 16.7L/min,与仪器标准流量误差在5%范围内 |
| `DEVICEJCVALUE_PM10` | 监测值PM10 | 颗粒物在线分析仪 / 16.7L/min,与仪器标准流量误差在5%范围内 |
| `DEVICEJCVALUE_PM25` | 监测值PM25 | 颗粒物在线分析仪 PM25 / 16.7L/min,与仪器标准流量误差在5%范围内 |
| `DEVICEWCVALUE_PM10` | 误差PM10 | 颗粒物在线分析仪 / 16.7L/min,与仪器标准流量误差在5%范围内 |
| `DEVICEWCVALUE_PM25` | 误差PM25 | 颗粒物在线分析仪 PM25 / 16.7L/min,与仪器标准流量误差在5%范围内 |

**平台校验器：**`DEVICEBZVALUE_CO`=required；`DEVICEBZVALUE_NO2`=required；`DEVICEBZVALUE_O3`=required；`DEVICEBZVALUE_PM10`=required；`DEVICEBZVALUE_PM25`=required；`DEVICEBZVALUE_SO2`=required；`DEVICEJCVALUE_CO`=required；`DEVICEJCVALUE_NO2`=required；`DEVICEJCVALUE_O3`=required；`DEVICEJCVALUE_PM10`=required；`DEVICEJCVALUE_PM25`=required；`DEVICEJCVALUE_SO2`=required；`DEVICEMODEL_CO`=required；`DEVICEMODEL_DT`=required；`DEVICEMODEL_LJ`=required；`DEVICEMODEL_NO2`=required；`DEVICEMODEL_O3`=required；`DEVICEMODEL_PM10`=required；`DEVICEMODEL_PM25`=required；`DEVICEMODEL_SO2`=required；`DEVICEWCVALUE_CO`=required；`DEVICEWCVALUE_NO2`=required；`DEVICEWCVALUE_O3`=required；`DEVICEWCVALUE_PM10`=required；`DEVICEWCVALUE_PM25`=required；`DEVICEWCVALUE_SO2`=required

## RF_Y_DEVICECHANGE
- 实体文件：`ReportForms/RF_Y_DEVICECHANGE.cs`
- 视图：Views/ReportForms/RF_Y_DeviceChange.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 | 设备预计 修回时间 / 备注 |
| `PROJECT` | 项目 | 项目 |
| `CHECKDATE` | 检查时间 |  |
| `CONDITION` | 设备维修情况 | 维修情况 |
| `FLOWCHECK` | 流量检查 | 流量检查 / 颗粒物标准膜校准 |
| `SPANCHECK` | 跨度检查 | 零点检查 / 跨度检查 |
| `STATIONID` | 站点ID |  |
| `ZEROCHECK` | 零点检查 | 零点检查 / 跨度检查 |
| `CHANGETIME` | 备机更换时间 | 备机 厂家及型号 / 备机 更换时间 |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `CALIBRATION` | 颗粒物标准膜校准 | 流量检查 / 颗粒物标准膜校准 |
| `INSTALLTIME` | 设备安装时间 | 原设备 厂家及型号 / 设备 安装时间 |
| `PROCESSTYPE` | 处理方式（1：现场维修/调试，2：更换备机，3：其他） |  |
| `DEVICEMODEL1` | 原设备厂家及型号 | 原设备 厂家及型号 / 设备 安装时间 |
| `DEVICEMODEL2` | 备机厂家及型号 | 备机 厂家及型号 / 备机 更换时间 |
| `EXCHANGETIME` | 设备预计修回时间 | 设备预计 修回时间 / 备注 |
| `FAILURECAUSE` | 故障原因 | 故障原因 |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
| `RFYDEVICECHANGEID` | 流水号 |  |

**平台校验器：**`CALIBRATION`=required；`DEVICEMODEL1`=required；`DEVICEMODEL2`=required；`FLOWCHECK`=required；`SPANCHECK`=required；`ZEROCHECK`=required

## RF_Y_DEVICEREPAIR
- 实体文件：`ReportForms/RF_Y_DEVICEREPAIR.cs`
- 视图：Views/ReportForms/RF_Y_DeviceRepair.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `SLOPE` | 斜率 |  |
| `AREAID` | 省市区 |  |
| `REMARK` | 备注 |  |
| `BACKTIME` | 返回时间 | 返回时间 |
| `CHECKDATE` | 检查时间 |  |
| `INTERCEPT` | 截距 |  |
| `SPANDRIFT` | 24小时跨度飘移 |  |
| `STATIONID` | 站点ID |  |
| `ZERODRIFT` | 24小时零点飘移 |  |
| `CREATEDATE` | 创建日期 |  |
| `DEVICENAME` | 更换零件名称 | 更换零件名称 |
| `REPAIRTIME` | 检修时间 | 检修时间 |
| `REVIEWDATE` | 复核时间 |  |
| `SPANDRIFT2` | 跨度飘移 | 跨度飘移 |
| `ZERODRIFT2` | 零点飘移 | 零点飘移 |
| `AUDITORDATE` | 审核时间 |  |
| `DEVICEMODEL` | 检修分析仪型号/编号 | 检修分析仪型号/编号 |
| `PROCESSTYPE` | 处理方式 |  |
| `COEFFICIENTR` | 相关系数r |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `REPAIRPROCESS` | 故障原因和检修过程 | 故障原因和检修过程 |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `REPAIRPHENOMENON` | 故障现象 | 故障现象 |
| `SPANDRIFTSATISFY` | 跨度飘移是否满足要求 | 是否满足要求 |
| `WORKINGORDERCODE` | 工单号 |  |
| `ZERODRIFTSATISFY` | 零点飘移是否满足要求 | 是否满足要求 |
| `RFYDEVICEREPAIRID` | 流水号 |  |

**平台校验器：**`COEFFICIENTR`=required；`DEVICEMODEL`=required；`DEVICENAME`=required；`INTERCEPT`=required；`SLOPE`=required；`SPANDRIFT`=required；`SPANDRIFT2`=required；`SPANDRIFTSATISFY`=required；`ZERODRIFT`=required；`ZERODRIFT2`=required；`ZERODRIFTSATISFY`=required

## RF_Y_PreventiveMaintenance
- 实体文件：`ReportForms/RF_Y_PreventiveMaintenance.cs`
- 视图：Views/ReportForms/RF_Y_PreventiveMaintenance.cshtml

| 列 | 含义（实体注释） | 视图标签 |
| --- | --- | --- |
| `ID` |  |  |
| `AREAID` | 省市区 |  |
| `HAS_CO` |  |  |
| `HAS_NO` |  |  |
| `HAS_O3` |  |  |
| `HAS_PM` |  |  |
| `REMARK` | 备注 | 维护总结： |
| `HAS_SO2` |  |  |
| `CHECKDATE` | 检查日期 |  |
| `STATIONID` | 站点ID |  |
| `CREATEDATE` | 创建日期 |  |
| `REVIEWDATE` | 复核时间 |  |
| `AUDITORDATE` | 审核时间 |  |
| `PROCESSTYPE` | 处理方式/类型 |  |
| `PREPARERDATE` | 填报时间(单据每次点保存更新的时间) |  |
| `REVIEWUSERID` | 复核人 |  |
| `AUDITORUSERID` | 审核人 |  |
| `POLLUTANTTYPE` |  |  |
| `PREPARERUSERID` | 填表人 |  |
| `OPERATIONSUNITID` | 运维单位ID |  |
| `WORKINGORDERCODE` | 工单号 |  |
