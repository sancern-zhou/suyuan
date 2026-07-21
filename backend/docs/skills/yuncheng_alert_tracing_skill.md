# 运城市告警溯源分析 Skill

## 概述
用于在运城市小时盯守告警触发后，基于证据目录中的告警 JSON、上下文资产、气象和本地后向轨迹分析结果生成提示性溯源分析报告，并在同一证据目录导出 Word 文档和微信摘要。

## 使用场景

当运城市小时盯守发布的告警状态为 `has_alert=true` 且 `status=pending_trace` 时，事件任务使用助手模式直接执行本 skill。助手模式调用专家子 Agent 分析，在同一证据目录生成报告、Word 文件和微信摘要，并返回事件任务服务要求的广播产物；事件任务服务负责广播和接收用户的对话上下文持久化。

## 场景流程

1. 运城小时盯守任务持续采集和判断告警。
2. 盯守脚本每次抓取都创建证据目录：`backend/backend_data_registry/scenarios/yuncheng_trial/{YYYYMM}/{YYYYMMDD_HHMMSS}/`。
3. 证据目录内写入 `{YYYYMMDD_HHMMSS}_alert.json`；无告警也保留该文件并写明 `has_alert=false`、`status=silent`。
4. 有告警时在同一证据目录抓取上下文资产并输出 `tracing_context_manifest.json`。
5. 告警发布后，事件任务使用助手模式直接执行本 skill，并通过可信事件上下文传入告警路径、上下文 manifest 路径和证据目录作为报告目录。
6. 助手模式读取正式 skill 和输入资产。
7. 助手模式调用专家子 Agent 分析，生成气象和常规分析草稿。
8. 助手模式在同一证据目录生成报告、Word 文件和微信摘要。
9. 助手模式确认 Word 文件存在后，返回事件任务服务要求的广播正文和 Word 附件路径。
10. 事件任务服务负责广播，不直接调用微信、广播或通知工具；广播服务将结果推送给配置的微信用户并写入各自的社交主会话。

## 输入

- `evidence_dir`: 证据目录，格式为 `backend/backend_data_registry/scenarios/yuncheng_trial/{YYYYMM}/{YYYYMMDD_HHMMSS}/`
- `alert_json_path`: `{evidence_dir}/{YYYYMMDD_HHMMSS}_alert.json`
- `tracing_context_manifest_path`: `{evidence_dir}/tracing_context_manifest.json`
- `report_dir`: 必须等于 `evidence_dir`
- `{YYYYMMDD_HHMMSS}_alert.json`
- `tracing_context_manifest.json`
- manifest 中列出的监测、气象、图像和预报资产
- `trajectory_analysis.json` 和 `trajectory.png`，由本地后向轨迹分析工具生成
- 气象分析专家子 Agent 草稿：`weather_analysis_draft.md`
- 常规分析专家子 Agent 草稿：`routine_analysis_draft.md`
- 告警 JSON 的 `rule_hits` 是触发告警的主规则
- 告警 JSON 的 `supporting_rule_hits` 是辅助解释线索，只能作为提示性证据

## 业务边界

- 不确认具体污染源。
- 不写“某企业导致污染”。
- 业务报告必须面向驻场团队、管理人员和业主代表，优先回答“发生了什么、影响多大、接下来做什么”。
- 技术判断必须能追溯到“监测事实、气象提示、可能影响因素、需要补充确认的信息”，但对外章节标题应使用业务化表达。
- 如果关键资产缺失，必须在报告中写入“需要补充确认的信息”，不要使用“数据缺口与不确定性”作为业务报告章节标题。
- 第一版小时盯守只抓取城市小时数据，不抓取站点数据。
- 第一版不得输出“某站点数据无效”“某站点仪器异常”等站点质控结论。
- 不重新判断告警是否成立，告警触发以脚本输出为准。

## 助手模式 SOP

助手模式必须按以下顺序执行，不能跳步，也不能在最终产物完成前返回中间状态：

1. 校验输入路径：
   - `evidence_dir` 必须存在。
   - `alert_json_path` 必须存在，且文件名必须匹配 `*_alert.json`。
   - `tracing_context_manifest_path` 必须存在。
   - `report_dir` 必须等于 `evidence_dir`。
2. 固定本次产物路径：
   - `weather_draft_path = {evidence_dir}/weather_analysis_draft.md`
   - `routine_draft_path = {evidence_dir}/routine_analysis_draft.md`
   - `report_qmd_path = {evidence_dir}/report.qmd`
   - `report_docx_path = {evidence_dir}/report.docx`
3. 读取本 skill、告警 JSON、`tracing_context_manifest.json` 和 manifest 中列出的所有可用资产；如果存在 `fire_hotspots.json`，只能将其作为周边生物质燃烧、露天焚烧或热异常影响的提示性证据，不得据此确认具体污染源或责任主体。
4. 只做输入一致性校验，不重新判断告警是否成立；如果告警 JSON 不是 `has_alert=true` 且 `status=pending_trace`，返回失败 JSON，不生成报告。
5. 同步调用气象 expert 子 Agent，要求输出 `weather_draft_path`。调用时必须在 goal 中明确要求专家 Agent 先阅读 `backend/docs/skills/weather_analysis_expert.md`，并按 Skill 中的"运城告警溯源场景资产要求"表读取和分析所有图片资产，将分析结果和图片引用写入草稿。
6. 同步调用常规 expert 子 Agent，要求输出 `routine_draft_path`。调用时必须在 goal 中明确要求专家 Agent 先阅读 `backend/docs/skills/routine_monitoring_analysis_expert.md`，并按 Skill 中的"运城告警溯源场景资产要求"表读取和分析所有图片资产，将分析结果和图片引用写入草稿。
7. 读取两个专家草稿，检查是否存在越界结论、AQI 口径错误、缺失资产未说明、驻场建议不可执行等问题。
8. 生成 `report_qmd_path`，并确保报告以“污染过程时间线”为核心，包含“本次告警概览、污染过程时间线、当前情况与未来趋势、可能影响因素、现场行动安排、需要补充确认的信息、附件与数据来源”。
9. 使用标准报告包能力导出 Word：读取 `backend/app/tools/report/report_package/references/index.md`，调用 `create_report_package` 保存报告包，调用 `render_report_package(format="docx")` 导出 Word，并用 `validate_report_package(require_docx=true)` 验收。
10. 验收 `report_docx_path` 必须存在；不存在时返回失败 JSON，不允许返回成功。
11. 生成 500 字以内微信摘要。
12. 返回“助手模式返回要求”中的事件广播 JSON，由事件任务服务负责推送微信正文和 Word 附件。

## 专家子 Agent 调度

主 Agent 不直接一次性完成全部分析，必须先调用两个 expert 模式子 Agent 生成草稿：

**强制调度约束**：

- 必须使用同步 `call_sub_agent` 调用专家子 Agent，且 `target_mode` 必须为 `expert`。
- 禁止使用 `spawn`、`wait_task` 或任何后台任务方式调用专家子 Agent。
- 禁止使用 `spawn` 后先向事件任务服务返回“专家正在后台并行执行”等中间状态。
- 助手模式必须等待两个 `call_sub_agent` 调用均完成、两个草稿文件均存在并通过读取校验后，才能继续生成最终 `report.qmd`、导出 `report.docx` 并返回结果。
- 助手模式在任务完成前不得返回中间状态；只能在最终报告和 Word 均完成后返回“助手模式返回要求”中的 JSON。

### 专家资产分工

主 Agent 调用专家子 Agent 时，必须把对应资产路径和分析任务写进 prompt；不得只笼统说“读取 manifest”。专家 Agent 必须先阅读分工内的 JSON 文件，并在草稿中插入分工内要求入稿的图片 Markdown 引用；不存在的资产必须在草稿中说明缺失及影响。

| 资产 | 文件名 | 负责专家 | 用途 |
| --- | --- | --- | --- |
| 告警状态 | `*_alert.json` | 两个专家都读 | 确认告警时间、污染物、触发规则和分析窗口；不重新判断告警是否成立。 |
| 目标城市小时数据 | `target_city_pollutants.json` | 常规分析专家主责，气象专家可引用 | 判断告警前后 AQI、主导污染物和分项污染物变化。 |
| 周边城市小时数据 | `nearby_city_pollutants.json` | 常规分析专家主责，气象专家可引用 | 判断区域同步抬升、周边城市联动和输入风险。 |
| 城市污染物空间分布图 | `city_pollutant_choropleth.png` | 常规分析专家主责 | 展示告警目标污染物在运城市与周边城市的空间分布。图片存在时，常规分析草稿必须插入图片并说明实际有效时次、区域差异和业务意义。 |
| 气象历史 | `meteorology_history.json` | 气象分析专家主责 | 判断温度、湿度、风、降水等实况条件。 |
| 后向轨迹 | `trajectory_analysis.json`、`trajectory.png` | 气象分析专家主责 | 判断潜在输送方向；草稿必须插入 `trajectory.png` 并写图注。 |
| 风场图 | `wind_field.png` | 气象分析专家主责 | 判断告警时段风向风速和输送条件；草稿必须插入并写图注。 |
| 能见度、降水、雷达 | `visibility.png`、`rainfall_24h.png`、`radar_mosaic.png`、`radar_composite_reflectivity_003.png` | 气象分析专家主责 | 判断湿清除、降水回波、低能见度或天气过程影响；存在时必须逐图说明。 |
| 水汽和降水预报 | `precipitable_water_000.png`、`precipitation_forecast.png`、`precipitation_forecast_024.png`、`precipitation_forecast_048.png`、`precipitation_forecast_072.png`、`hourly_precipitation_forecast.png` | 气象分析专家主责 | 判断未来降水清除和天气变化趋势；草稿至少引用对判断有价值的图片，并说明未引用图片原因。 |
| 风和温度预报 | `wind_forecast_024.png`、`wind_forecast_048.png`、`wind_forecast_072.png`、`national_tmax_forecast.png`、`national_tmin_forecast.png` | 气象分析专家主责 | 判断未来扩散、输送和光化学生成条件；草稿至少引用关键风场或温度图。 |
| 卫星火点 | `fire_hotspots_summary.json`、`fire_hotspots_map.png`、`fire_hotspots.json` | 常规分析专家主责，气象专家辅助判断输送方向 | 优先读取摘要和分布图，完整明细只作附件核查；作为周边燃烧或热异常线索，不得确认具体污染源。常规草稿存在火点时必须插入 `fire_hotspots_map.png`。 |
| 未来气象预报 | `forecast_meteorology.json` | 气象分析专家主责 | 判断后续 1-5 天气象变化和风险持续性。 |
| 空气质量预报 | `air_quality_24h_forecast.json` | 常规分析专家主责 | 判断未来 24 小时空气质量风险、触发污染物和阈值超出污染物是否需要持续盯守。 |

1. 气象分析专家子 Agent
   - 执行前阅读通用专家 skill：`backend/docs/skills/weather_analysis_expert.md`。
   - 按“专家资产分工”读取气象历史、后向轨迹、风场、能见度、降水、雷达、水汽、风温预报、未来气象预报等资产。
   - 必须在草稿中插入并分析存在的核心图片：`trajectory.png`、`wind_field.png`、`visibility.png`、`rainfall_24h.png`、`radar_mosaic.png`、`radar_composite_reflectivity_003.png`、`precipitable_water_000.png`、`precipitation_forecast*.png`、`hourly_precipitation_forecast.png`、`wind_forecast_*.png`、`national_tmax_forecast.png`、`national_tmin_forecast.png`；如图片较多，至少保留对研判最有价值的图片并说明筛选依据。
   - 负责回答：
     - 告警前后是否存在静稳、弱风、逆温提示、高温强辐射、湿清除不足或降水影响。
     - 后向轨迹和风场显示了什么方向，对当前关注方向有什么影响。
     - 未来 1-6 小时和当天后续扩散、降水清除、光化学生成条件是否有利或不利。
     - 哪些气象图像应进入最终报告，并给出每张图的业务化图注建议。
   - 气象专家不得确认具体污染源；如引用火点资产，优先读取 `fire_hotspots_summary.json` 和 `fire_hotspots_map.png`，只能结合风向/轨迹说明火点线索是否位于可能输送方向。
   - 生成 `{report_dir}/weather_analysis_draft.md`。
   - 草稿必须包含“监测事实引用、气象提示、传输推断、图片图注建议、需本地数据核实”五类内容。
   - 返回最小 JSON：

```json
{
  "expert_type": "weather",
  "draft_path": "{report_dir}/weather_analysis_draft.md"
}
```

2. 常规分析专家子 Agent
   - 执行前阅读通用专家 skill：`backend/docs/skills/routine_monitoring_analysis_expert.md`。
   - 按“专家资产分工”读取告警 JSON、目标城市小时数据、周边城市小时数据、城市污染物空间分布图、卫星火点摘要与分布图、空气质量预报；可引用气象专家草稿或气象资产，但不主导气象机制判断。
   - 如果 `city_pollutant_choropleth.png` 存在，必须在草稿的周边联动分析中插入 `![城市污染物空间分布](city_pollutant_choropleth.png)`，并写明图片实际有效时次、目标污染物、运城市与周边城市的主要空间差异及其对现场盯守的意义；不得仅列入附件清单。
   - 必须读取并分析 `air_quality_24h_forecast.json`；如文件存在，草稿必须说明未来 24 小时 AQI、首要污染物、触发污染物和阈值超出污染物变化。
   - 必须读取 `fire_hotspots_summary.json` 和 `fire_hotspots.json`；如火点数量大于 0，草稿必须概括数量、方向、最近距离、最高 FRP 或最接近时段，并插入 `fire_hotspots_map.png`。
   - 负责回答：
     - 告警前 6 小时内目标城市 AQI 和各污染物如何变化，主导因子是什么。
     - 周边城市是否同步抬升，是否更像区域过程、本地累积或混合影响。
     - `fire_hotspots_summary.json` 是否存在周边火点线索；如有，概括数量、方向、距离、时间接近性，并建议插入 `fire_hotspots_map.png`；如无，写明“未见卫星火点线索”。
     - 未来空气质量预报是否提示风险延续，驻场团队应如何安排盯守和核查。
     - 报告中各时间阶段的污染变化、周边情况、业务关注点和现场行动应写哪些要点。
   - 常规专家不得输出站点质控结论，不得确认具体污染源；火点只能作为燃烧源提示，必须写明需本地巡查、秸秆焚烧管控、工地/企业/道路等本地信息确认。
   - 生成 `{report_dir}/routine_analysis_draft.md`。
   - 草稿必须包含“告警事实、污染变化、周边联动、火点线索、未来风险、现场建议、证据边界”七类内容。
   - 返回最小 JSON：

```json
{
  "expert_type": "routine",
  "draft_path": "{report_dir}/routine_analysis_draft.md"
}
```

主 Agent 只依赖 `expert_type` 和 `draft_path` 定位专家草稿。详细分析、图表说明、证据限制和不确定性必须写在草稿文档中。

## 主 Agent 审核整合

- 读取两个专家草稿后再生成最终 `report.qmd`。
- 检查两个草稿是否存在跨领域越界结论；越界内容不得直接进入最终报告。
- 检查 AQI 口径、驻场建议可执行性、需要补充确认的信息是否完整。
- 检查 `city_pollutant_choropleth.png`：图片存在时，常规分析草稿和最终 `report.qmd` 都必须引用该图片，且最终引用必须位于“污染过程时间线”的周边联动节点或该节点内的周边联动正文，不得只出现在附件清单。
- 如两个专家结论冲突，最终报告必须写明“证据不一致或不足”，不得强行给出确定结论。
- 最终结论、微信摘要和 Word 导出由主 Agent 统一完成。

## AQI 口径

- AQI 告警使用 `AQI 小时值` 口径，触发条件为 `AQI > 100`，对应空气质量进入轻度污染及以上水平。
- `AQI > 100` 是综合空气质量指数超标提示，不等同于单项污染物小时浓度超过 100。
- 报告中必须同时写明首要污染物或主要贡献污染物；如果资产中没有首要污染物字段，只能写“需结合分项污染物确认主导污染因子”。
- 分析 AQI 告警时，优先对照 PM2.5、PM10、O3、NO2、SO2、CO 的小时变化，避免把 AQI 告警直接归因到单一污染物。

## 污染过程时间线生成规则

- 以 `target_city_pollutants.json` 中目标城市小时数据作为主时间轴。
- 先读取告警时间、监测数据范围以及所有资产的实际有效时次，再划分本次过程阶段。
- 候选阶段为“告警前背景、污染开始变化、污染加速或持续、告警触发时刻、告警后最新变化、未来数小时趋势”；没有对应数据的阶段不得生成，相邻阶段无法区分时必须合并。
- 每个阶段标题必须写明实际时间点或时间范围，并按“变化—同期情况—业务意义”组织内容：说明当时发生了什么、同期天气和周边区域如何，以及下一时段应关注或采取什么行动。
- 周边城市和气象小时数据优先挂接到相同小时；只有最近有效时次可用时，必须直接说明与主时间轴的时间差，不强行对齐。
- 轨迹按受体时刻挂接，火点按卫星观测时间挂接，图片按图中或元数据中的有效时次挂接，禁止用文件抓取时间替代业务有效时间。
- 预报统一放在未来阶段，并写明起报时间、预报时效和对应未来时间范围，不得与历史实况混写。
- 无法确认有效时次的资产不得推动正文判断，可放入附件，并在“需要补充确认的信息”中说明。

## 业务版报告结构

最终 Word 报告面向业务人员，不写成技术日志或算法复盘。章节必须使用以下结构：

1. 本次告警概览
   - 用 3-5 句话说明告警时间、污染物、等级、当前关注点和是否建议现场加密盯守。
   - 给出一句业务判断，例如“本次告警更偏向高温光化学累积风险，暂不能确认具体污染源”。

2. 污染过程时间线
   - 这是报告篇幅最大的核心章节，按实际时间点或时间范围串联目标城市监测变化、同期气象、周边城市、轨迹、火点和相关图片。
   - 时间阶段必须由实际数据动态形成；数据不足时合并或省略阶段，不制造时间节点。
   - 每个节点只回答三个业务问题：当时发生了什么、同期情况如何、对下一时段的盯守或行动意味着什么。
   - 趋势表格可放在对应时间节点内，只保留业务人员判断变化所需的关键数值。

3. 当前情况与未来趋势
   - 说明目标城市最新监测数据更新到何时、当前处于持续、转折还是缓解状态。
   - 预报必须标明起报时间、预报时效和对应未来时间窗，只用于说明未来变化和行动安排。

4. 可能影响因素
   - 将原“初步溯源研判”改写为业务表达。
   - 可写本地累积、区域传输、光化学生成、颗粒物二次转化或燃烧源提示等可能因素。
   - 如 `fire_hotspots_summary.json` 中有火点记录，可加入“周边卫星火点线索”作为可能影响因素之一，并插入 `fire_hotspots_map.png`；如无记录，可写为“本次未见周边高置信火点线索”。
   - 每条都要写清“支持依据”和“还需要什么本地信息确认”，不得确认具体污染源。

5. 现场行动安排
   - 每条建议必须可执行，至少包含：建议时间窗、核查范围、现场动作、补充数据、升级条件。
   - 建议时间窗：写清“立即”“未来 1-2 小时”“当天夜间”等具体执行时段。
   - 核查范围：写清上风向、周边城市联动方向、重点道路/工业片区/施工区域等范围；没有本地清单时写“建议由驻场团队按本地清单匹配”。
   - 现场动作：写清巡查、走航、企业工况核实、扬尘源排查、移动源管控建议、加密会商等动作。
   - 补充数据：写清需要补充的站点小时数据、污染源清单、企业门禁、卡口、走航、执法巡查、组分或雷达数据。
   - 升级条件：写清 AQI 或主导污染物连续上升、周边同步抬升、静稳持续、后向轨迹指向明确等触发升级会商或现场核查的条件。

6. 需要补充确认的信息
   - 替代“数据缺口与不确定性”。
   - 用业务语言说明哪些结论当前不能拍板，例如：缺本地污染源清单、企业门禁、卡口、移动源轨迹、执法巡查、走航、站点小时数据。
   - 说明这些信息补齐后可以帮助确认什么问题。

7. 附件与数据来源
   - 简短列出本次报告使用的告警 JSON、manifest、监测数据、气象数据、预报数据和图片。
   - 数据来源用于回溯，不作为正文重点；同时列出所用资产的实际有效时次或时间范围。

## QMD 输出要求

- 输出文件名为 `report.qmd`。
- 必须包含可渲染的 YAML header。
- 源 QMD 的图片地址按实际文件位置计算：先设置 `report_qmd_path = Path(report_dir) / "report.qmd"`，再从 manifest 的资产项获得 `image_path`，确认 `Path(image_path).is_file()`，然后使用 `source_image_ref = Path(image_path).resolve().relative_to(report_qmd_path.parent.resolve()).as_posix()` 得到 Markdown 引用地址。当前抓取脚本把图片与源 QMD 放在同一证据目录，因此计算结果通常是裸文件名，例如 `![后向轨迹](trajectory.png)`、`![能见度](visibility.png)`。
- 如果 `relative_to(report_qmd_path.parent)` 无法计算，先把图片复制到 `report_qmd_path.parent` 的受管子目录，再重新计算相对路径。图片引用始终来自真实文件路径与 QMD 目录的相对关系，不根据文件名猜测目录层级。
- 调用 `create_report_package` 时，把每张入稿图片的真实绝对路径传入 `create_report_package.assets`。报告包工具复制完成后，从工具结果的 `copied_assets[].relative_path` 获取发布稿引用；例如返回 `assets/charts/trajectory.png` 时，发布稿使用该路径。
- 调用 `create_report_package` 前，逐一解析 `report_qmd_path.parent / source_image_ref` 并确认文件存在；调用后执行 `validate_report_package`。如果工具返回 `Report image validation failed`、缺失引用、解析路径或 `Could not fetch resource`，根据 `resolved_path` 和 `repair_hint` 重新定位真实图片、更新源 QMD 引用或 `assets` 参数，再次打包并校验。
- 图片紧跟其对应的时间节点，不集中陈列。
- 图片存在时，最终 `report.qmd` 必须在“污染过程时间线”的周边联动节点或该节点内的周边联动正文中展示 `city_pollutant_choropleth.png`；图注必须说明实际有效时次、目标污染物、运城市与周边城市的主要空间差异及其业务意义，不得仅在附件清单中列名。
- 只选取能解释节点变化或支持下一步行动的图片，不以覆盖全部资产为目标；存在与过程直接相关且时次明确的图片时，正文至少插入 1 张。
- 每张图片必须配业务化图注，说明实际有效时次、图上主要情况以及对现场关注的意义。
- 无法确认有效时次、与本次过程无直接关系或不存在的图片不得占位，也不得用于推动正文判断；其影响写入“需要补充确认的信息”。
- 表格使用 Markdown 表格。
- 不使用需要联网加载的资源。
- 缺失的资产不得留空占位，必须在“需要补充确认的信息”章节说明。

## 助手模式返回要求

助手模式不直接调用微信、广播或通知工具。确认 Word 文件存在后，必须只向事件任务服务返回以下 JSON；`media` 必须只包含 `report.docx` 的绝对路径：

```json
{
  "success": true,
  "broadcast": {
    "message": "500字以内微信摘要",
    "media": ["/absolute/path/to/report.docx"]
  }
}
```

如果输入缺失、专家草稿缺失、报告导出失败或 Word 验收失败，必须返回失败 JSON，不得返回成功：

```json
{
  "success": false,
  "error": "失败原因"
}
```

## 微信摘要要求

微信正文控制在 500 字以内，格式：

```text
【运城市空气质量告警】
时间：
污染物：
等级：
结论：
建议：
报告：见附件 Word。
```
