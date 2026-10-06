# -*- coding: utf-8 -*-
"""Mark the B/C landing package as SHIPPED in the survey report (idempotent)."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPORT = r"E:\Tools\suyuan-jiangsu\源库表单勘察报告.md"
MARKER = "### 落地记录（2026-10-04 已实施）"

SECTION = """

### 落地记录（2026-10-04 已实施）

用户确认"可以，实施"当日完成，**同步范围 40 张 ODS + 13 张 mart/dim**：

- 4 表入 sync_config.json（全部 daily_full，已入 sync-daily.cmd 全量清单与对账清单）：
  qc_backorderarrangelog（窗口式，10,248 行）、bsd_supply（768）、bsd_moniter_parameter（428，开 SCD2 快照，快照总数 19→20）、dev_scrap（1）
- 2 新模型：mart_qc_backorder_analysis（10,248 行，城市/站点维度经 dim_station）、
  dim_device_parameter（271 行 = 428 剔除 157 空参数名；devicemodel_id 安全转数值；model_device_count）
- dim_device 增加 device_model_id 列（打通 站点设备→型号参数 join，12,143 行可关联），dim_device.yaml 同步更新
- MODEL_TESTS +6、dq_check 覆盖 +2（共 70 项 0 失败）；白名单 11→13（contract.txt 7,605 字节）；后端已重启加载无错
- E2E（agent_reader 直查）：补测风暴近 7 天 = 3081A 高邮文体中心 30 条/1 天、3104A 泗阳奥体中心 30 条/1 天；
  3079A 诊断路径 = dim_device→dim_device_parameter 取到光室温度[56,60]℃、倍增管高压[-1200,500]V 等参数清单
- 新坑：dbt post_hook 的 COMMENT 字符串漏收尾单引号，解析不报错、建表时才炸（unterminated quoted string），已修复
- 待平台确认（不阻塞使用）：qc_backorderarrangelog 的 state/datatype 枚举语义、bsd_moniter_parameter 的 parameterid 字典来源
"""

t = open(REPORT, encoding="utf-8").read()
if MARKER in t:
    print("already present, skip")
else:
    with open(REPORT, "a", encoding="utf-8", newline="\n") as f:
        f.write(SECTION)
    print("appended; report lines:", len(open(REPORT, encoding="utf-8").read().splitlines()))
