# create_report_chart 正式分析图表扩展设计

## 1. 背景与目标

`create_report_chart` 当前面向 Word/QMD 正式报告提供稳定的静态图片，已经支持柱状图、折线图、散点图、饼图、堆叠图、直方图、热力图、箱线图、表格图片及若干环境领域图表。现有实现只能在单张图片中使用一种基础几何图形；即使使用 `dual_axis_line`，左右轴上的系列也都是折线。传入多个 `data.charts` 时，工具会主动拆成多张图片。

本次扩展优先解决正式分析报告中的高频表达缺口，不追求图表类型大全。第一期目标是让常规柱线组合、区间带、瀑布和帕累托等图表可以直接通过 `create_report_chart` 生成，不再回退到任意 Python 绘图，同时继续保证 A4 Word 缩放后的可读性、输入契约的简洁性和旧调用的兼容性。

## 2. 范围

### 2.1 第一期开启的图表类型

| 优先级 | `chart_type` | 能力与典型用途 |
| --- | --- | --- |
| P0 | `combo` | 柱线组合、双轴柱线、分组柱加趋势线、堆叠柱加折线 |
| P0 | `range_line` | 均值与上下限、置信区间、目标区间、浓度波动范围 |
| P0 | `waterfall` | 同比变化贡献、增减因素、预算或排放变化拆解 |
| P0 | `pareto` | 问题来源排序、累计贡献率、重点污染源识别 |
| P1 | `diverging_bar` | 同比增减、正负偏差、改善与恶化对比 |
| P1 | `step_line` | 阶段标准、政策阈值、状态随时间阶梯变化 |
| P1 | `error_bar` | 均值与误差、监测结果不确定性、组间比较 |

`combo` 第一期只组合柱和线，但同时覆盖单轴、双轴、分组柱、多折线以及堆叠柱加折线。它是一个受控组合协议，不是任意 Matplotlib 或 ECharts 配置入口。

### 2.2 明确不在第一期范围内

- 雷达图、仪表盘、漏斗图、桑基图和树图。
- 三维图、科研专用图和任意 Matplotlib 参数透传。
- 三个或更多 Y 轴。
- 同一图片中的多个独立子图或仪表板布局。
- 将饼图、散点图或其他几何图形混入 `combo`。
- 改变 `data.charts` 的既有拆图行为。

上述需求继续使用既有专用工具或 `execute_python`；是否纳入 `create_report_chart` 由后续独立设计决定。

## 3. 方案选择

评估过三种路线：

1. 为每种组合变体增加独立 `chart_type`。实现直接，但 `bar_line`、`dual_axis_bar_line`、`stacked_bar_line` 等类型会持续膨胀并产生重复代码。
2. 使用受控的组合图协议。新增通用 `combo`，由每个系列声明几何类型和坐标轴；结构特殊的图表继续使用独立类型。
3. 引入类似 ECharts 的完整绘图配置。表达能力最强，但会破坏当前简单输入和稳定报告版式的边界。

采用方案 2。它能覆盖最常见的组合需求，同时把可用几何、坐标轴数量、系列数量和版式规则限制在工具可验证的范围内。

## 4. 数据契约

### 4.1 通用原则

- `data` 继续使用简单、显式的数组和系列对象，不接受完整 ECharts option。
- 现有 `bar`、`line`、`dual_axis_line` 等调用协议和渲染路径保持不变。
- 新字段只在对应的新 `chart_type` 中解释，不改变旧图型对同名字段的处理。
- 分类轴和各系列的数组长度必须一致。
- 所有数值必须是有限数；不接受 NaN 和无穷值。
- 自动排序、累计和派生值必须写入结果 metadata，避免静默改变数据含义。

### 4.2 `combo`

```json
{
  "chart_type": "combo",
  "title": "销售额与增长率",
  "data": {
    "labels": ["一季度", "二季度", "三季度", "四季度"],
    "series": [
      {
        "name": "销售额",
        "type": "bar",
        "values": [120, 150, 180, 210],
        "axis": "left"
      },
      {
        "name": "增长率",
        "type": "line",
        "values": [8.2, 12.5, 9.6, 15.1],
        "axis": "right"
      }
    ]
  },
  "options": {
    "left_y_label": "销售额（万元）",
    "right_y_label": "增长率（%）"
  }
}
```

约束如下：

- `series[].type` 必填，只允许 `bar` 或 `line`。
- `series[].axis` 可选，只允许 `left` 或 `right`，默认 `left`。
- `series[].values` 必填；长度必须与 `labels` 一致。
- 柱系列可以设置 `series[].stack`。相同且非空的 `stack` 值表示堆叠；未设置时为分组柱。
- 最多使用左右两个 Y 轴。
- 只要存在右轴，`options.left_y_label` 或 `options.left_unit` 与 `options.right_y_label` 或 `options.right_unit` 必须分别提供，避免双轴含义不清。
- 建议不超过 4 个系列。超过 4 个但不超过实现硬上限时允许渲染并返回警告；硬上限定为 6 个，超过时拒绝渲染。
- 折线绘制层级高于柱形，图例保持输入系列顺序。

### 4.3 `range_line`

```json
{
  "labels": ["1月", "2月", "3月"],
  "series": [
    {
      "name": "月均浓度",
      "values": [42, 38, 35],
      "lower": [35, 31, 29],
      "upper": [49, 45, 42]
    }
  ]
}
```

- 每个系列必须同时提供 `values`、`lower` 和 `upper`。
- 每个点必须满足 `lower <= values <= upper`。
- 第一期最多支持两个区间系列；两个系列使用不同的低透明度填充和清晰中线。

### 4.4 `waterfall`

基础输入为 `labels + values`。`values` 表示每一步的增减量，可选 `start_value` 指定初始基数，可选 `show_total` 控制是否自动添加最终总计柱，默认 `true`。

- 正值、负值、起始值和总计使用不同的语义样式。
- 工具自动计算每一步的基线、顶部位置和最终值，并将结果写入 metadata。
- 输入顺序具有业务含义，不自动排序。

### 4.5 `pareto`

基础输入为 `labels + values`。默认按值从高到低排序，绘制柱形和累计占比折线；右轴固定为 0–100%，默认绘制 80% 参考线。

- 值必须非负，合计必须大于 0。
- `options.sort` 默认 `descending`，允许设置为 `none` 保留业务顺序。
- metadata 返回实际排序顺序、累计值和累计占比。

### 4.6 `diverging_bar`

基础输入为 `labels + values`。以零线为视觉中心，正负值分别使用稳定的语义颜色。支持水平和垂直布局；默认根据标签长度沿用现有的横向切换规则。

### 4.7 `step_line`

沿用普通折线图的 `labels + values` 或多系列 `series` 协议。`options.step` 允许 `pre`、`mid`、`post`，默认 `post`。其余图例、标签和参考线规则复用普通折线图。

### 4.8 `error_bar`

使用 `labels + series`。每个系列提供 `values`，并使用以下两种误差形式之一：

- 对称误差：`errors`。
- 非对称误差：同时提供 `lower_errors` 和 `upper_errors`。

误差值必须为非负有限数。第一期默认以点和误差棒表达，不与柱形组合；需要柱形加误差棒时由后续 `combo` 协议扩展另行设计。

## 5. 模块设计

现有 `renderer.py` 保留统一入口、画布创建、文本治理、图片保存和返回结果组装。新能力按职责拆分，避免继续扩大单文件分派逻辑：

```text
create_report_chart/
├── renderer.py
├── validation.py
├── renderers/
│   ├── combo.py
│   ├── interval.py
│   └── analytical.py
└── references/
    ├── combo-chart.md
    ├── range-and-error.md
    ├── waterfall-chart.md
    ├── pareto-chart.md
    └── comparison-charts.md
```

职责如下：

- `validation.py`：`ChartDataError`、有限数检查、标签与系列长度检查、新图型专用的规范化函数。
- `renderers/combo.py`：`combo` 和复用组合基础设施的 `pareto`。
- `renderers/interval.py`：`range_line` 和 `error_bar`。
- `renderers/analytical.py`：`waterfall`、`diverging_bar` 和 `step_line`。
- `renderer.py`：根据标准化后的 `chart_type` 分派，应用通用 options、文本治理并保存图片。

本次只提取新图型实际需要共享的能力，不全面迁移或重写已有绘图函数。`ChartDataError` 移入 `validation.py` 后，由 `renderer.py` 重新导出或同步更新已有导入点，避免破坏工具层和测试层的现有依赖。

## 6. 渲染与版式规则

- 延续 Word 输出 5.8 英寸目标宽度、源画布缩放和现有中文字体选择。
- `combo` 采用统一系列颜色映射；柱形使用适当透明度，折线和标记位于上层。
- 左右轴共享分类轴并合并图例；图例顺序与输入系列顺序一致。
- 双轴颜色按数据系列区分，不把整个坐标轴渲染为高饱和对立颜色。
- `range_line` 使用低透明度区间填充和清晰中线，避免覆盖网格及其他系列。
- `waterfall` 绘制步骤连接线，并区分增加、减少、起始和总计。
- `pareto` 的右轴固定为百分比，80% 参考线标签不得遮挡累计线。
- `diverging_bar` 强调零线，正负颜色在彩色和灰度打印中均应可辨。
- `step_line` 复用折线图的标签稀疏、图例和网格策略。
- `error_bar` 的线宽、帽宽和标记大小以 Word 最终缩放后的可读性为准。
- 标题继续只接受语义标题；图号由报告组装层处理。

## 7. 错误与警告

### 7.1 拒绝渲染

以下情况返回失败结果和精确字段路径：

- 缺少必需字段、数组为空或系列长度不一致。
- 数值包含 NaN、无穷值或无法转换的内容。
- `combo` 出现未知系列类型、未知轴、第三坐标轴、超过 6 个系列或双轴缺少两侧含义。
- `range_line` 出现 `lower > values` 或 `values > upper`。
- `pareto` 出现负值或合计不大于 0。
- `error_bar` 出现负误差或只提供一侧非对称误差。

错误示例：

```text
combo.series[1].values 长度为 3，与 labels 长度 4 不一致。
combo 使用 right 轴时必须提供左右轴标题或单位。
pareto.values 的合计必须大于 0，无法计算累计占比。
error_bar.series[0].errors 不允许包含负数。
```

### 7.2 允许渲染并警告

以下情况生成图片，并通过 `layout_warnings` 返回稳定的机器可读警告码：

- 系列数为 5 或 6。
- 分类标签过多、过长或柱形预计过窄。
- 标题或图例文本过长。
- 左右轴量级差异异常。
- 两个区间系列重叠严重。

## 8. Metadata 与可审计性

每个新图型应至少返回：

- `requested_chart_type` 和 `applied_chart_type`。
- `series_count`、使用的几何类型和轴数量。
- 自动排序、自动堆叠、累计计算或横向切换等变换说明。
- 派生数据：瀑布累计位置、帕累托累计占比等。
- 文本治理结果及 `layout_warnings`。

metadata 不复制无必要的完整原始数据，但必须足以解释工具对输入做过的语义变换。

## 9. 文档与提示词

- 在工具 schema 的 `chart_type` 枚举中加入 7 个新类型。
- 将工具描述中的固定类型数量同步为实际枚举数量，或改为不易失真的“支持多种预定义图表类型”，避免扩展后继续显示旧数量。
- 更新 `data` 和 `options` 描述，提供 `combo` 的最小示例并强调不是 ECharts option。
- 在 `references/index.md` 和 `chart-types.md` 中增加路由和选择建议。
- 为新类型增加渐进式参考文档，说明输入、适用场景、限制和反例。
- 更新正式报告相关提示词：常规柱线组合、区间带、瀑布和帕累托优先使用 `create_report_chart`；只有超出受控协议的复杂图才回退到 `execute_python`。

## 10. 测试设计

### 10.1 Schema 与文档

- 7 个新类型出现在工具 schema 中。
- 每种类型均能从 `references/index.md` 路由到相应设计文档。
- schema 示例、参考文档和真实参数名保持一致。
- 报告提示词能把常规新图型路由到 `create_report_chart`。

### 10.2 数据校验

- 每种协议覆盖标准输入、空数据、长度不一致、NaN 和无穷值。
- 覆盖 `combo` 的系列类型、轴、堆叠、双轴单位、建议上限和硬上限。
- 覆盖区间上下界、帕累托零合计和负值、误差棒负误差及非对称误差缺边。
- 验证自动计算和排序结果进入 metadata。

### 10.3 渲染

- 每个新类型至少有一个标准案例和一个边界案例。
- `combo` 分别覆盖单轴柱线、双轴柱线、多柱加折线和堆叠柱加折线。
- 验证 PNG 文件存在、尺寸合理且不是空白图片。
- 验证返回的图型、系列数、轴数、派生数据和警告码。
- 运行现有全部 `create_report_chart` 检查，保证旧类型继续通过。

### 10.4 人工视觉验收

增加示例图集生成脚本，一次生成所有新图型的 Word 和 screen 两套 PNG。人工检查：

- Word 缩放后的字号和线宽。
- 图例遮挡和长标签处理。
- 双轴含义、区间覆盖和参考线标注。
- 彩色和灰度打印可辨识度。

不采用整张 PNG 的严格像素快照，以免字体和 Matplotlib 小版本差异造成脆弱测试。自动测试以结构化 metadata、图片尺寸、非空白检测和关键渲染行为为主。

所有构建和测试命令在项目指定的 Conda 环境 `/root/miniconda3/envs/backend_py311` 中执行。

## 11. 验收标准

- 7 个新 `chart_type` 均可通过 `create_report_chart` 直接生成正式报告图片。
- `combo` 覆盖约定的四种组合场景，并严格执行几何、坐标轴和系列数量限制。
- 旧调用协议、既有图型和 `data.charts` 拆图行为保持兼容。
- 新类型均具有 schema 描述、渐进式参考文档、错误示例和自动测试。
- 派生值和自动变换可通过 metadata 审计。
- 常规柱线组合、区间带、瀑布和帕累托图不再回退到 `execute_python`。
- 复杂科研图、多子图和任意自定义绘图仍明确路由到适合的工具。
