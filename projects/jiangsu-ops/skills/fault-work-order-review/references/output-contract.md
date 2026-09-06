# 故障工单审核输出契约

所有 SOP 分支最终都调用 `jiangsu_submit_fault_work_order_review`。不要调用其他提交工具。

## 必填字段

```json
{
  "sop_id": "SOP-01、SOP-02 或 SOP-03",
  "event_id": "事件 ID",
  "evidence_pack_path": "证据包路径",
  "work_order_code": "完整工单号",
  "station": {
    "station_code": "站点编码",
    "station_name": "站点名称"
  },
  "pollutants": ["污染物"],
  "gates": {
    "M1、E1 或 T1": {
      "status": "pass/fail/uncertain/not_applicable",
      "basis": "证据依据",
      "missing_evidence": ["缺失证据"],
      "scope": "core/supporting/rebuttal"
    }
  },
  "data_impact": [
    {
      "station_code": "站点编码",
      "device_id": "设备编号",
      "pollutant": "污染物",
      "granularity": "hour",
      "start": "异常或影响开始时间",
      "end": "异常或影响结束时间",
      "status": "affected/pseudo_value/missing/unaffected/uncertain",
      "decision": "keep/partial_exclude/exclude/missing_no_delete/not_applicable/needs_evidence"
    }
  ],
  "work_order_decision": "approve/reject/needs_evidence",
  "evidence_refs": ["证据引用"],
  "review_comment": "事实、缺口和审核意见"
}
```

## 核验项原则

- `core` 表示核心闭环核验项，核心闭环缺失时才可能阻断 `approve`。
- `supporting` 表示辅助证据，缺失时必须说明，但不应默认把结论降成 `needs_evidence`。
- `rebuttal` 表示反证线索，可用于推翻表面一致的说法。
- 核验项不是证据清单。只要核心闭环成立，就可以给出结论；辅助证据更适合写入 `basis`、`evidence_refs` 和 `review_comment`。
- 审核优先判断证据闭环，不优先放大工单文字瑕疵。若附件、截图、监测/审核标识、处置记录和影响边界已经相互印证，非实质性措辞不严谨只能写入备注或人工关注项，不得单独作为 `needs_evidence`。

### SOP-01 两类分析的输出映射

使用 `gates.M1` 至 `gates.M6` 的平铺结构，不新增分组字段，也不改变 `scope` 的含义。SOP-01 不审核流程节点：

- 事实一致性按 M1 对象、M2 失败事实、M6 数据标识、M3 处置、M4 复测组织；`basis` 记录实际发生的事实、与工单声明是否一致及证据引用。分别使用 `failure_fact`、`flag_boundary`、`disposal`、`retest` 承载对应摘要。
- 逻辑一致性集中在 M5；`basis` 按“数据有效性；污染物范围；时间段”分别写出判断及依据。具体处置写入 `data_impact`，剔除边界及其合理性写入 `exclusion_intervals`。事实已确认但数据影响尚不明确时，M5 如实填 `uncertain` 并列明缺口。
- M3 的 `basis` 和 `disposal` 应说明维护处置与附件证据的对应关系，具体附件引用写入 `evidence_refs`。

`review_comment` 开头继续遵循用户侧简化口径，详细分析依次写事实一致性、逻辑一致性。事实核验通过不自动意味着 M5 通过，M5 通过也不等于数据应保留。

SOP-02、SOP-03 同样不提交流程类核验项：SOP-02 使用 E1–E8，E1–E6 为事实一致性，E7–E8 为数据分类和边界判断；SOP-03 使用 T1–T7，T1–T6 为传输链事实一致性，T7 为数据分类和处置判断。处置、恢复、补传及时间戳相关附件或回执分别写入对应核验项的 `basis`、`evidence_refs` 和专用摘要字段。

## 通用字段

不维护 QC/ENV/TR 子分类编码，也不提交子分类字段。故障表现以业务语言写入 `failure_fact`、`disposal`、`recovery` 或 `transmission`；无法套用历史故障类型不属于证据缺口。

- `device_id`、`device_type`：从证据包设备对象或工单详单提取。
- `failure_fact`：只记录异常或失败事实，不写处置结论。
- `disposal`：只记录处置动作、时间和原因对应性。
- `retest`：SOP-01 使用，记录质控复测或校准后验证。
- `recovery`：SOP-02 使用，记录处置后恢复和稳定验证。
- `transmission`：SOP-03 使用，记录本地数据、平台接收、补传和时间戳连续性核验摘要。
- `flag_boundary`：记录状态标识、审核标识或质控标识的起止与核验状态。
- `review_summary`：一句话用户摘要，必须收敛为“审核结论 + 数据处置 + 核心原因”，不得罗列核验项编号或长证据清单。
- `scope`：核验项层级，建议核心核验项填 `core`，辅助证据填 `supporting`，反证线索填 `rebuttal`。

## 用户侧简化口径

右侧卡片总结展示审核结论、数据处置、核心原因、辅助核验和下一步，并展示事实一致性、逻辑一致性的分析依据与缺口。取消独立核验项页签和编号展示；`gates` 仅作为兼容现有接口的结构化字段。Agent 仍需提交结构化核验项和证据引用供追溯，但 `review_summary` 和 `review_comment` 的开头必须服务于用户快速判断：

- 审核结论只表达 `通过`、`退回修改` 或 `退回补材料`。
- 数据处置只表达 `保留`、`缺失不剔除`、`局部剔除`、`全部剔除`、`不适用` 或 `暂不处置`。
- 核心原因最多写 1 句，说明运维核心材料是否足以支撑申请。
- 辅助核验只表达 `一致`、`有矛盾`、`未覆盖` 或 `系统取证异常`；辅助证据缺失不得单独导致退回。
- 下一步只表达 `确认归档`、`确认剔除区间后归档`、`退回运维修改` 或 `退回运维补材料`。

## 数据剔除字段

仅提交小时数据有效性和小时剔除区间，`granularity` 固定为 `hour`。5分钟曲线可作为 `boundary_sources` 的参考证据，但不得生成分钟级 `data_impact` 或剔除区间；缺少小时有效性或小时边界依据时补证，不将分钟异常自动取整为小时剔除。

不需要提交 `exclusion_required`：系统按「任一 `data_impact.decision` 为 `partial_exclude` 或 `exclude`」自动判定。涉及剔除时，必须先在每条对应的 `data_impact` 中填写明确 pollutant、granularity、start、end，再提交逐条对应的 `exclusion_intervals`。`exclusion_intervals` 每条通过 `data_impact_index` 引用对应 `data_impact` 条目，不重复填写污染物、粒度和起止时间：

```json
{
  "exclusion_intervals": [
    {
      "data_impact_index": 0,
      "boundary_sources": [
        "station_5minute_raw:首次异常",
        "station_hour_audited:审核标识",
        "station_alarm_logs:告警恢复",
        "quality_control.task_details:复测合格"
      ],
      "reasonableness_check": {
        "status": "pass/uncertain/fail",
        "basis": "为什么该区间合理或仍不确定"
      }
    }
  ]
}
```

每个 `partial_exclude` 或 `exclude` 的 `data_impact` 条目都必须有一个对应的 `exclusion_intervals` 条目；不得写“见工单”“待确认”“故障期间”等模糊边界。系统会展开成完整剔除区间供人工确认，并在本站监测曲线和同城对比曲线上标注该起止时间。同样不得把工单创建时间、故障处理时间、取证窗口起止或工单申请剔除区间直接写成剔除边界。它们只能作为待核验线索。SOP-03 中“离线”“未上传”“无数据”不能直接形成剔除区间；传输中断但本地数据完整且补传成功时应优先判断 `keep`，无测量或本地缺失时应优先判断 `missing_no_delete`。

## 结论状态

- `approve`：对应 SOP 的核心核验项均有足够证据，工单审核结论和数据处置均可人工确认归档；SOP-01 不以流程节点作为通过条件。
- `reject`：处置、对象、证据或流程存在明确错误，当前结论不应通过。
- `needs_evidence`：运维核心材料缺失、会影响事实/分类/处置/边界判断的关键证据冲突或边界不明，需要退回补材料；仅系统主动抓取的辅助证据缺失，或不影响结论的工单措辞瑕疵，不得单独使用该结论。

## 证据引用

使用可回溯引用，避免泛泛写“见证据包”：

- `work_order_detail:<工单号>`
- `monitoring.station_5minute_raw:<时间或字段>`
- `monitoring.station_hour_audited:<时间或字段>`
- `quality_control.task_details:<r_id>`
- `station_alarm_logs:<告警时间或字段>`
- `station_environment_history:<时间或字段>`
- `same_city_monitoring.station_hour_raw:<城市或时间>`
- `transmission.local_data:<时间或字段>`
- `transmission.platform_receipt:<时间或字段>`
- `transmission.retransmission:<补传批次或时间>`
- `transmission.timestamp_continuity:<时间或字段>`
- `attachment:<工单号>:<附件名>`
- `evidence_gap:<数据组>/<项目>`
