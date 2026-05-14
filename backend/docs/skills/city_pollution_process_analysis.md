# 城市污染过程自动分析技能

## 定位

本技能属于溯源项目，不属于 Codex 客户端技能。用于 `pollution_event_monitor` 生成的城市污染过程证据包。脚本负责事件识别、数据质量检查、事件去重和证据包生成；智能体负责解释、归纳、证据矩阵、假设排序、置信度和管控建议。

不要把本技能放到 `.codex/skills`。项目内固定位置为：

`backend/docs/skills/city_pollution_process_analysis.md`

## 触发条件

当用户、定时任务或 `analysis_request.md` 提到以下内容时使用本技能：

- 城市污染过程识别告警
- `evidence_pack.json`
- `analysis_request.md`
- 自动分析污染过程
- 数据质量检查后的污染过程解释
- 定时巡检发现异常后需要假设验证

## 输入

优先读取 `evidence_pack.json`。如果只拿到事件目录，读取该目录下的 `evidence_pack.json`。如果只拿到运行目录，读取 `run_manifest.json` 并选择其中的 `event_artifacts[].evidence_pack`。

常见伴随文件：

- `event.json`
- `city_hour_monitoring.json`
- `data_quality_report.json`
- `station_hour_monitoring.json`
- `weather_hourly.json`
- `pm25_components.json`，如存在
- `vocs_components.json`，如存在

重点读取 `evidence_pack.json` 中的：

- `event`
- `event.event_lifecycle`
- `quality_gate`
- `observed_signal_summary`
- `data_files`
- `data_refs`
- `fetch_errors`
- `suggested_evidence_gaps`

## 总原则

算法负责发现事实，助手负责解释事实。不要重新发明告警算法、事件去重算法或阈值规则，也不要跳过证据直接归因。

必须区分：

- 观测事实：数据中直接可见的时间、浓度、站点、气象、组分变化
- 算法判断：事件类型、触发规则、生命周期状态、质量门禁
- 推理判断：基于事实推导的可能机制
- 不确定性：缺失数据、反证不足、证据冲突
- 后续动作：建议继续查询或现场核查的对象

## 质量门禁

必须先应用 `quality_gate`：

- `status=fail`：不得写确定性污染来源；总置信度最高为低；重点转为数据质量核查。
- `status=caution`：机制判断最高为中，除非有强独立证据；必须说明哪些问题压低置信度。
- `status=pass`：允许正常推理，但每个结论仍必须有证据引用。

不得超过 `quality_gate.max_confidence`。`interpretation_limits` 中的限制必须写入“不确定性”或“数据质量影响”。

## 工作流程

### 1. 读取证据包

建立证据清单：

| 证据类型 | 文件 | 是否可用 | 主要字段 | 用途 |
|---|---|---|---|---|
| 事件摘要 | event.json |  |  | 起止、主污染物、触发规则 |
| 城市小时数据 | city_hour_monitoring.json |  |  | 城市浓度变化、协同污染 |
| 数据质量 | data_quality_report.json |  |  | 缺测、恒值、突刺、异常关系 |
| 站点小时数据 | station_hour_monitoring.json |  |  | 空间同步、领先站点、高值站点 |
| 气象数据 | weather_hourly.json |  |  | 风速风向、湿度、降水、边界层 |
| PM2.5组分 | pm25_components.json |  |  | 二次无机盐、碳组分、扬尘线索 |
| VOCs组分 | vocs_components.json |  |  | O3 前体物、OFP/反应活性线索 |

### 2. 复述事件事实

简短复述算法事实，不要泛泛描述：

- 城市
- 事件生命周期状态：`new / ongoing / updated / ended / routine`
- 事件时间段
- 主污染物
- 峰值和峰值时间
- 触发规则
- 上升速度或持续时长
- 是否多污染物同步变化
- 站点是否同步、是否有领先站点
- 风速、风向、湿度、降水、边界层等关键气象
- 质量门禁和解释限制

### 3. 按污染物选择推理策略

这一步由智能体根据证据自主选择，不要写死固定流程。

PM2.5 / PM10 常见假设：

- 低风速或低边界层下本地累积
- 上风向或周边城市先升导致区域传输
- PM10 更强、风速较高或地壳组分高导致扬尘/道路尘影响
- 硫酸盐、硝酸盐、铵盐、OC/EC、湿度或氧化指标支持二次生成
- 单站偏离、PM2.5 大于 PM10、长时间恒值或缺测导致数据异常

O3 / O3_8h 常见假设：

- 高温、强辐射、低云量和前体物条件下光化学生成
- 上风向城市或站点 O3 先升导致区域输送
- NO2/VOCs 变化提示 NO 滴定、VOCs/NOx 敏感性或前体物限制
- O3 模式与同城站点或气象条件冲突导致数据异常

NO2 / CO / SO2 常见假设：

- NO2/CO 短时峰值提示交通或近源排放
- SO2/CO/NO2 与风向站点时序一致时提示工业或燃烧源影响
- 多污染物低风速同步上升提示本地累积
- 单站孤立尖峰且缺少气象/同站支持时优先考虑数据或超局地问题

多污染物事件按时间链判断：

- PM 与 NO2/CO 同步上升：本地累积或燃烧影响更可信
- 午后 O3 上升且 NO2 下降：光化学生成更可信
- PM 在上风向城市后升且风向一致：区域传输更可信
- 单污染物单站异常：数据质量或超局地源需优先核查

### 4. 建立竞争假设

至少提出 2 个、最多 4 个可检验假设。每个假设必须写成：

```text
假设：
如果为真，应该看到：
当前支持证据：
当前反证/不足：
还需补充：
```

至少包含一个反向假设，例如数据异常、本地短时冲击、区域传输、本地累积、光化学生成、扬尘影响、工业/交通近源影响等。

### 5. 验证和反证

按假设逐项核查，不要只找支持证据。

必须检查：

- 时间链路：污染物是否先升、同步升、滞后升
- 空间链路：站点之间是否同步，是否有明显高值站或领先站
- 气象链路：风速、风向、湿度、降水、边界层条件是否支持机制
- 污染物链路：PM2.5/NO2、PM10/PM2.5、O3/NO2、CO/NO2 等是否符合假设
- 组分链路：离子、OC/EC、VOCs 类别是否支持二次生成、燃烧源、扬尘或臭氧生成潜势
- 数据质量：缺测、突刺、长时间恒定、PM2.5 大于 PM10 等是否影响结论

证据强度标记只能用：

- `supports`
- `weakly_supports`
- `contradicts`
- `insufficient`

### 6. 必要时主动补证

优先使用证据包已有文件。只有当具体证据缺口会影响假设排序时，才主动调用工具或查询数据。

补证目标示例：

- 周边城市或上风向城市小时数据
- 更细站点小时数据
- 气象预报、边界层、风场
- 后向轨迹或输送路径
- 上风向企业
- PM2.5 离子/碳组分/地壳组分/PMF
- VOCs 组分/OFP/OBM

补证后必须写入“补证记录”：查了什么、为什么查、结果如何改变或没有改变判断。

## 输出格式

最终输出必须包含：

```markdown
## 城市污染过程自动分析

### 事件概况

### 可引用事实

### 假设验证矩阵
| 假设 | 支持证据 | 反证/不足 | 验证结果 | 置信度 |
|---|---|---|---|---|

### 污染来源研判

### 反证与不确定性

### 补证记录

### 数据质量影响

### 管控与核查建议
```

置信度只能使用 `高`、`中`、`低`。

`高` 只能用于至少两类独立证据一致，且 `quality_gate.max_confidence` 允许高置信度的结论。

## JSON 输出

如需要机器可读结果，写入 `reasoning_result.json`：

```json
{
  "event_id": "...",
  "quality_gate": {"status": "pass", "max_confidence": "high"},
  "observed_facts": [
    {"fact": "...", "source": "weather_hourly.json", "field": "records[].measurements.wind_speed_10m"}
  ],
  "hypothesis_ranking": [
    {
      "hypothesis": "local_accumulation_under_low_wind",
      "rank": 1,
      "confidence": "medium",
      "supporting_evidence": ["F1", "F2"],
      "counter_evidence": ["F3"],
      "missing_evidence": ["boundary_layer_height"]
    }
  ],
  "confidence": "medium",
  "counter_evidence": ["..."],
  "follow_up_actions": ["..."],
  "unwritable_claims": ["..."]
}
```

## 写回文件

如果有事件目录写权限，必须在 `evidence_pack.json` 同目录写入：

- `reasoning_analysis.md`

如调用方要求结构化结果，同时写入：

- `reasoning_result.json`

## 禁止事项

- 不要仅凭“浓度升高”直接判定来源。
- 不要把相关性写成确定因果。
- 不要忽略 `quality_gate` 和数据质量问题。
- 不要在没有组分、风向、站点空间证据时声称明确源解析。
- 不要把算法事件类型原样当作最终结论，必须重新验证。
- 不要把 `suggested_evidence_gaps` 当作已经证实的结论。
- 不要重新判断事件是否该告警或是否该合并。

## 快速调用范式

当定时任务触发时：

1. 调用 `city_pollution_event_monitor(city="广州", hours=24)`。
2. 读取返回的 `event_artifacts[].evidence_pack`。
3. 按本技能完成假设验证。
4. 将结果写入同目录 `reasoning_analysis.md`。
5. 回复用户时只摘要核心发现、置信度和下一步建议。
