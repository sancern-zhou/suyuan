# 故障工单审核提交协议

所有 SOP 使用 `submit_task_review`。分析完成后调用工具提交一次；工具返回 `success=true` 才表示结果已保存并生成待人工确认卡片。最终文字回复只报告提交结果，不再承载系统回填字段。

## 字段填写

- `subject_id`：完整工单号。同一工单的重新审核沿用此编号。
- `event_id`：当前触发事件 ID。
- `category`：`工单审核`。
- `title`：站点名称与工单审核标题。
- `summary`：一句话说明“审核结论 + 数据处置 + 核心原因”。
- `decision`：`approve`、`reject` 或 `needs_evidence`。
- `comment`：审核意见，依次说明事实一致性、逻辑一致性、缺口与下一步。
- `review_basis`：例如 `["SOP-01"]`。
- `checks`：核验项数组。每项包含 `name`、`status`、`basis`、`scope`、`missing_evidence`。`status` 为 `pass/fail/uncertain/not_applicable`；`scope` 为 `core/supporting/rebuttal`。至少一项，名称和依据非空。SOP-01 使用 M1–M6，SOP-02 使用 E1–E8，SOP-03 使用 T1–T7，并附中文名称。
- `data_impact`：按污染物填写数组；无数据影响可为空。
- `evidence`：证据包、附件、图表文件的数组，每项为 `{"label":"说明","path":"文件路径"}`。文件须存在于当前数据目录；不填 URL 或虚构路径。
- `actions`：人工下一步操作建议数组。
- `sections`：通用详情区块数组，格式为 `{"title":"故障事实","fields":[{"label":"异常表现","value":"实际事实"}]}`。站点/设备、故障事实、处置、恢复、复测、传输、标识边界、同区对比均用区块表达，不新增顶层字段。值必须为文字，复杂事实分成多个字段。

任务结果字段要求中，`sections.work_order_no` 与 `sections.sop_id` 为必填：在详情区块分别添加 `key="work_order_no"`（完整工单号）和 `key="sop_id"`（SOP-01、SOP-02 或 SOP-03）。工具校验失败时按错误修正并重新提交。

不提交任务 ID、执行 ID、人工状态或自定义 `success`；由运行上下文和工具生成。

## 数据影响与剔除

每条 `data_impact` 必须填写：

- `pollutant`、`basis`、`decision`；结论枚举为 `keep/partial_exclude/exclude/missing_no_delete/not_applicable/needs_evidence`。
- 可选 `station_code`、`device_id`；`granularity` 在工单审核中固定为 `hour`。
- `start/end` 同时提供或同时省略；采用含时区的 ISO 时间，例如 `2026-09-10T08:00:00+08:00`，开始不晚于结束。
- 建议剔除时，必须有明确时间区间、非空 `boundary_sources` 数组、`reasonableness_status`（`pass/uncertain/fail`）、非空 `reasonableness_basis`。

剔除边界和合理性直接填写在对应数据影响项中，不再维护重复的区间数组。人工归档时统一面板要求核验剔除区间。

5 分钟数据只能作为分析参考，不能输出分钟级剔除建议，也不能将分钟异常自动取整为小时区间。缺少小时有效性或边界依据时如实补证。

## 判断原则

核心闭环不足才阻断通过；辅助证据缺失应明确说明，不能机械退回。工单文本瑕疵在已被附件、截图、记录与边界充分解释时只列为备注。

事实一致性与数据逻辑判断分开；事实核验通过不自动意味着数据保留或剔除。标识是被审核对象，不能代替原始数据与其他事实证据。

SOP-01 分别核验对象、失败事实、标识、处置、复测，并在 M5 判断数据有效性、污染物范围及时间段。SOP-02 核验事实和数据分类边界；SOP-03 区分设备未测量、已测量未上传、平台暂不可见、补传成功及时间戳异常。

不得自动回写平台工单状态或剔除监测数据。`needs_evidence` 是可提交的业务结论，不等于工具执行失败。
