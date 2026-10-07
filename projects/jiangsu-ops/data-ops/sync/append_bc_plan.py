# -*- coding: utf-8 -*-
"""Append B/C-domain application plan to the survey report (idempotent)."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPORT = r"E:\Tools\suyuan-jiangsu\源库表单勘察报告.md"
MARKER = "2026-10-04 B/C 域表单应用方案"

SECTION = """

---

## 附录二：2026-10-04 B/C 域表单应用方案（画像详版）

**决策记录**：数据获取率/有效率/传输率/接收率以平台接口为准（`jiangsu_query_statistics` → GetStationEffectiveRateQueryDataPage 等三端点），**不再自建统计**；原批次3候选 mart_data_capture_analysis 取消。dat_* / aud_* / air_livedata 维持未同步，仅作备查。

画像脚本：`sync/profile_bc_tables.py`。

### B. 质控域

**1. qc_backorderarrangelog（质控补测/回调安排日志）——推荐同步 + 建 mart_qc_backorder_analysis**
- 粒度：站点×小时×污染物一行，带 state(1/2/3/6)、start/end 小时、operator；窗口内 10,248 行、96 站（比质控试点 23 站大得多）、每日活跃。
- 现状缺口：mart_qc_execution_analysis 到"合格/不合格"为止，看不到平台事后处置；这是质控闭环的下游环节。
- 应用：a) 不合格→补测安排→补测状态 闭环链路（uniquecode 95/96 可 join qc_historyresult）；b) 补测风暴预警——3079A 窗口内 9 天 2,248 条、3081A 10 天 958 条，集中异常信号可直接进运维监督日报；c) 补测响应/完成率统计。
- 接入注意：uniquecode 是任务组代码（安排表 3,618 行仅 105 个值），**不可** join qc_arrangeresult 行级；state/datatype 枚举语义需平台确认（数据形状推测 1=待执行/2=已完成/6=持续回调；datatype 与工具 data_type 0/1/2/3 枚举不同，另含 6）。
- 成本：daily_full 窗口全量（约1万行），一张小宽表，约半天。

**2. bsd_supply（质控耗材台账）——ODS-only，观察级**
- 站点耗材（滤膜380/聚四氟乙烯滤膜209/硅胶/纸带）领用更换记录，syyy=用途（巡检/周巡检），54 站。
- 应用：故障诊断上下文（该站最近一次滤膜/硅胶更换时间）、耗材超期旁证。
- 数据现实：supplynum/usednum 全 0、workingordercode 窗口内 100% 空、名称有脏值（'\\t'尾随）——数据太薄，先同步观察，变厚再建模。

**3. bsd_parts——不建议同步**：全量仅 29 行，含"备件测试"行，partname 大面积为空、数量全 0，疑似测试数据。

### C. 设备诊断域

**4. bsd_moniter_parameter（设备型号×健康参数阈值字典）——推荐同步 + 建 dim_device_parameter**
- 内容：38 设备型号 × 178 参数 × 121 参数名的 toplimit/lowlimit/warntoplimit/warnlowlimit/unit（采样流量、斜率/截距、光室温度、反应室温度、转换炉温度、紫外灯电压、倍增管高压、参比/测量信号…），428 行。
- 应用：a) **station_fault_diagnosis 增强**——alm_rule 只覆盖污染指标告警阈值，本表补"设备健康参数"维度：诊断站点故障时列出该站设备型号应检参数与正常范围，结合监测曲线/巡检读数判越限；b) **smart_inspection**——按设备型号生成巡检参数核对表，对齐 pw_taskitem 巡检项。
- 关联已验证：devicemodel = bsd_device.devicemodelid（16,237 行命中）；37% statusname 为空需在 dim 层清洗排除；parameterid(178) 与 statusname(121) 数量不一致，参数名字典来源需平台确认。
- 成本：daily_full 字典全量，一张 dim 小表 + 契约更新，约半天。

**5. DEV_SCRAP（报废审批）——随 log_device 场景顺带同步**
- 1 行（X24063@3099A，2026-07-21，维修成本过高寄回原厂），设备生命周期终点事件；与已同步的 log_device（运行/故障/备机流转）组成完整生命周期，P1"备机更换及时性"的设备退出分支。ODS-only 即可。

### 建议最小落地包（待用户 go）

同步 4 张：qc_backorderarrangelog、bsd_supply、bsd_moniter_parameter、DEV_SCRAP（全部 daily_full 小表）；跳过 bsd_parts。
建 2 个数据产品：mart_qc_backorder_analysis（补测闭环+风暴预警）、dim_device_parameter（诊断/巡检参数清单）。
待平台确认：qc_backorderarrangelog 的 state/datatype 枚举、bsd_moniter_parameter 的 parameterid 字典来源。
"""

t = open(REPORT, encoding="utf-8").read()
if MARKER in t:
    print("already present, skip")
else:
    with open(REPORT, "a", encoding="utf-8", newline="\n") as f:
        f.write(SECTION)
    print("appended; report lines:", len(open(REPORT, encoding="utf-8").read().splitlines()))
