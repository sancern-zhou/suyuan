# execute_python 工具指导手册

助手Agent和社交Agent在使用 `execute_python` 处理复杂计算、Excel、可视化或文件生成前，应先阅读本手册。简单的纯 Python 计算可直接调用。

每次执行环境独立，变量和文件挂载不会跨调用保留。读取输入文件时，必须在本次调用的 `input_files` 参数中声明全部输入；只允许当前会话数据文件或已授权资源文件，不接受目录。工具校验后挂载文件，并将规范化绝对路径注入代码中的 `input_files` 列表，支持循环读取和动态拼接路径。相对输入路径统一以项目根目录为基准，无需读取文件时可省略该参数。

## 适用场景

绘图先匹配业务图型，再按模式选择通用工具。属于已支持的六种专用业务图型时，必须使用 `create_business_chart`，此规则优先于模式默认绘图工具。六种图型为 `aqi_calendar`、`pollutant_calendar`、`pollutant_wind_rose`、`generic_pollutant_wind_rose`、`wind_timeseries`、`weather_timeseries`。其他通用或自定义图表：问数模式以 `execute_echarts_python` 为主；专家和报告模式以 `execute_python` 为主，ECharts 辅助交互探索。

不得用 Python 或 ECharts 重新实现这些业务模板来绕过专用工具；需要数据准备时可先用 Python 清洗、计算并 `save_data`，再交给业务工具。组合报告可复用业务工具生成的图片素材。专用工具不可用、调用失败或输入不足时，先补齐数据、修正调用或说明限制，不自动换工具重画同一模板。尚未支持的新业务图型及超出现有契约的自定义分析图可使用 Python，并明确与现成业务图型的区别；不能仅通过改名规避规则。

- 数据处理：`pandas`、`numpy`、`scipy`。
- Excel 读取、修改和生成：优先使用 `openpyxl`，读取分析可用 `pandas`。
- 主要静态绘图：使用 `matplotlib` / `seaborn` 生成通用分析和自定义报告图表，通过 `save_chart` 保存并自动归档。已支持的专用业务图型必须使用 `create_business_chart`；交互探索使用 `execute_echarts_python`。
- 报告中间资源生成：图表、表格、结构化 JSON、qmd 草稿片段。
- 一次性 Office 文件生成：仅当用户明确要求 Word/Excel 文件，且不需要 qmd 同源报告包时使用。
- 自定义统计：仅当专用查询/统计工具无法直接满足时使用。

## 正式报告边界

正式报告不要通过 `execute_python` 直接交付 DOCX，也不要在 Python 脚本中手写格式转换流程。

标准流程：

1. 用查询工具和 `execute_python` 完成计算、表格整理和通用报告静态绘图；匹配已支持的专用业务图型时必须使用 `create_business_chart`。
2. 准备 `report.qmd` 内容，图片最终使用报告包内相对路径，例如 `assets/charts/chart_01.png`。
   不要根据 `/api/image/{image_id}` 或缓存 id 推断这个路径；应把真实图片文件路径传给
   `create_report_package.assets`，必要时用 `name` 指定 `chart_01.png`，由报告包工具复制并规范化引用。
3. 调用 `create_report_package` 保存为 `reports/{report_id}/report.qmd` 并触发右侧面板预览。
4. 用户在右侧面板点击下载 QMD/Word，或点击分享生成报告预览链接。

## 一次性 DOCX 兼容格式

只有用户明确要求一次性 Word 文件，且不需要 qmd 同源报告包时，才直接使用 `python-docx`。此时默认使用公共样式工具，避免每次由模型重新决定字体和段落格式。

```python
from docx import Document
from app.services.report.government_docx_style import (
    apply_government_report_style,
    add_government_title,
    add_government_heading,
    add_government_paragraph,
    add_government_table,
    add_government_image,
    resolve_report_image_path,
)

doc = Document()
apply_government_report_style(doc)
add_government_title(doc, "报告标题")
add_government_heading(doc, "一、总体情况", level=1)
add_government_paragraph(doc, "正文内容。")
add_government_table(doc, [["指标", "数值"], ["PM2.5", "30"]])
doc.save("backend/backend_data_registry/report.docx")
```

默认规范：标题小标宋/宋体 fallback、二号居中；正文仿宋三号、首行缩进2字符、固定28磅行距；一级标题黑体三号，二级标题楷体三号，三级标题仿宋加粗三号；页边距上3.7cm、下3.5cm、左右2.8cm。用户明确要求其他格式时，在默认样式基础上局部覆盖。

### DOCX 图片嵌入

正式报告的 Word 导出由报告 API 处理，一般不需要手写图片嵌入逻辑。只有在直接用 `python-docx` 从零生成一次性 Word 文件时，才需要显式调用图片工具：

```python
from pathlib import Path
from docx import Document
from app.services.report.government_docx_style import (
    apply_government_report_style,
    add_government_image,
)

doc = Document()
apply_government_report_style(doc)
image_path = Path("backend/backend_data_registry/charts/demo.png")
add_government_image(doc, image_path, caption="图1 示例图")

doc.save("backend/backend_data_registry/reports/demo/report.docx")
```

## 文件路径

- 生成文件必须保存到项目可访问目录，优先使用 `backend/backend_data_registry/`。
- 禁止保存到 `backend_data_registry/`，该目录在仓库根目录下，前端下载和后端文件管理不会以它作为标准输出目录。
- 代码中打印中间资源保存路径，便于后续工具传给 `create_report_package`。
- 工具会检测 `backend/backend_data_registry/` 中新增文件。

## 输出产物 Schema

- `files`：本次生成文件的项目相对真实归档路径列表；后端路径显式包含 `backend/` 前缀。
- `file_path`：主文件的真实归档路径，用于预览、下载或传给后续工具，必须原样复用。
- `generated_artifacts`：生成产物的结构化交付状态；`auto_published=true` 表示已自动登记到会话资源目录。
- `pdf_preview`：Office/PDF 文件预览信息，适用于 `.docx/.xlsx/.pptx/.pdf`。
- `visuals`：图片或 ECharts 可视化块；`matplotlib` 图片会缓存为 `/api/image/{image_id}`。

生成文件由 `execute_python` 自动归档并发布，不需要再调用 `publish_session_file`。禁止根据文件名自行拼接
`backend/backend_data_registry/sessions/...` 路径；需要资源 ID 时使用 `list_session_resources` 查询。

正式报告必须使用标准报告包结构：

```text
backend/backend_data_registry/reports/{report_id}/report.qmd
```

不要直接写成根目录文件或绕过报告包：

```text
backend/backend_data_registry/reports/{report_id}.qmd
```

生成正式报告时，调用 `create_report_package`，不要把本地绝对路径作为最终交付方式。

## Python 绘图风格约束

Python 是专家和报告模式的主要通用绘图工具，图型由分析问题和数据条件决定；问数模式通用图以 ECharts 为主。已支持的专用业务图型在所有模式中必须使用 `create_business_chart`。正式报告图与业务图表共用 `REPORT_THEME` 和 `SERIES_COLORS`，matplotlib/seaborn 的默认主题在执行前自动注入。

- 字体：系统自动选择支持中文的字体，与报告图表一致；不要硬编码 SimHei 或用不支持中文的字体替代。
- 字号：标题 14 pt、轴标签 11 pt、刻度/图例 9.8 pt、数据标签 10.5 pt、注释 8.5 pt。报告嵌入缩放后仍须可读，必要时增大字号或拆分图表。
- 配色：常规系列使用 `SERIES_COLORS`；强调、风险、正向和背景色使用 `theme_color('primary'/'warning'/'danger'/'positive'/'grid')`。相同变量跨图颜色一致；环境质量等级颜色及浓度分级必须遵守下节环境绘图约束；变化量和相关系数使用合适的顺序或发散色图，并提供色标和单位。
- 版式：白底、标题左对齐、弱化轴线、轻网格、无图例边框；避免装饰背景和无分析必要的 3D。默认画布 7.2 × 4.6 英寸，按数据密度和报告版面调整比例。
- 导出：通用主题默认 160 DPI；预计进入报告的 PNG 显式使用 `save_chart(fig, filename, dpi=240)`，细节密集或印刷场景可用 300 DPI。白底、紧边界，使用返回值和工具最终归档路径交付资源，不自行拼接存储路径。
- 标题不写“图1”等编号，编号由报告层负责；轴标签包含单位，说明时间范围、样本口径、缺失处理和数据来源。相关关系不直接解释为因果，不编造贡献率或置信区间。
- `seaborn.set_theme()` 会覆盖默认设置，须在创建 Figure 前调用 `apply_report_style()` 恢复主题。工具也注入 `REPORT_THEME`、`SERIES_COLORS` 和 `theme_color()`，可直接复用；保存时保留代码选择的图型和布局。
- 交付前查看生成图，检查中文缺字、裁切、标签重叠、图例遮挡和报告缩放后的可读性；出现问题先调整再入报告。

### 报告插图尺寸与比例

- 专家模式生成的静态图也应预留进入报告的需求。绘图前按最终插入宽度设计，已有报告模板时遵循模板正文宽度；未知时以 A4 纵向单栏、约 5.8 英寸（14.7 cm）为参考，不依赖用户在页面放大后阅读。
- 常规趋势、柱状和散点图优先横向单图，宽高比约 1.4–1.8；可从 `plt.subplots(figsize=(6.0, 3.8))` 开始，图例、轴标签和注释所需空间也计入最终图片。主题默认画布是通用起点，报告图应显式设置 `figsize`。
- 排名、长类别名和热力图可增加高度，必要时按合理类别或时段拆成独立图片。避免超宽画布、过长图片和大面积留白；图片连同图注应适合报告单页，不能靠缩小整图塞入页面。只有报告模板明确支持时才采用跨栏或横向页面。
- 以最终插入尺寸验收字号：刻度、图例和数据标签一般不小于 9 pt，轴标签不小于 10 pt，标题不小于 12 pt。估算最终字号 = 绘图字号 × 插入宽度 / 导出图片实际宽度（英寸）；`bbox_inches='tight'` 和外置图例可能改变实际宽度，须查看最终导出图。若缩放后过小，应调整画布、字号、标签密度或拆图。
- 图例通常放在图下方，预留底部空间；长图例分行排列，避免横向撑宽图片。标题保持简短，数据来源、评价口径和长说明放入报告图注，图内保留理解图表所需的单位和标准线标签。
- DPI 改善栅格清晰度，不能补救物理尺寸过小。报告 PNG 在约 5.8 英寸宽度下宜有约 1400–1800 像素宽；导出后按正文实际宽度检查可读性，不只检查原图或放大预览。

## 环境领域绘图约束

本节与通用报告主题共同适用，通过现有工具文档传递，不依赖新增模式提示词。环境标准配置集中在 `backend/config/environment_chart_standards.json`，辅助函数实现位于 `backend/app/utils/environment_charts.py`，可供 Python 和业务图表共用。

### 配色与图例

- AQI/IAQI 等级使用 HJ 633 附录 A 的 RGB 色值：优 `#00E400`、良 `#FFFF00`、轻度 `#FF7E00`、中度 `#FF0000`、重度 `#99004C`、严重 `#7E0023`。禁止为迎合主题任意淡化、替换等级色。缺测使用灰色 `MISSING_COLOR`，不能表示为“优”。
- 浓度等级图按污染物及平均时间对应的 IAQI 浓度断点映射；不得把浓度直接套入 AQI 数值区间，也不得将 IAQI 等级等同于环境质量达标结论。用 `pollutant_color` 做映射；`get_pollutant_scale(pollutant=..., average_time=..., observed_on=..., unit=...)` 返回浓度/IAQI 断点、等级色和来源，供构造分级色标、图例。图注说明 HJ 633—2026 及浓度统计口径。
- 多污染物、多站点趋势图使用固定系列色，保持跨图一致。等级颜色用于等级色带、超限点或状态提示，不必把所有浓度折线分段染成等级色。贡献率、相关系数、变化量不使用 AQI 等级色。
- 每张图必须有足以解释颜色、系列、符号和参考线的图例、色标或直接标注。系列图必须有图例，默认图下方居中、多列，无边框，不遮挡数据、坐标标签或图注。`legend_below(ax, *other_axes)` 可收集双轴系列并按标签去重；先设置系列 `label`，在坐标和布局设置完成后调用。多子图为各图例留足间距。
- 连续热力图必须有带单位的色标；等级热力图使用固定分级图例并标出区间，不能用各图数据最小/最大值重新拉伸等级颜色。纯 AQI 等级图可通过 `AQI_COLORS`、`AQI_LABELS` 构造 `matplotlib.patches.Patch`，传给 `legend_below` 的 `handles`/`labels`。污染物图的区间必须使用该污染物的浓度断点，不能标作 AQI 数值区间。

### 标准限值与评价口径

- 浓度趋势和对比图有适用环境质量限值时必须标出横向虚线，并说明标准编号/版本、阶段、等级、平均时间、数值和单位。先明确功能区适用等级，不能无依据默认二级。无适用限值的指标（如相关系数、贡献率）不生成标准线。
- `get_environment_limit(pollutant=..., average_time=..., grade=..., observed_on=..., unit=...)` 返回限值、完整标签及官方来源。`average_time` 为 `1h`、`24h`、`daily_max_8h`、`annual`；内置标准不支持的组合会报错。不能用月平均直接代替年平均，也不能把臭氧普通 8 小时滑动平均直接当作日最大 8 小时平均。
- `add_standard_limit(ax, data_average_time=..., **上述参数)` 绘制限值线并确保它在坐标范围内。平均时间不匹配时拒绝绘制；若仅需小时曲线与日均限值的参考对照，显式传 `reference_only=True`，标签会声明“不作该时段达标判定”。双轴图须在浓度所属轴调用，单位必须与该轴数据一致。
- 管理目标、预警阈值和标准限值使用不同名称和线型，注明来源；不得将自行设定目标冠以国标限值。多污染物不同限值分别绘制；过多时拆分子图。
- 当前仅内置环境空气六项基本污染物及 GB 3095/HJ 633 的 2026 版本，不保留 2012 版口径。数据/情景日期须不早于 2026-03-01；GB 3095 至 2030 年底使用过渡限值，2031 年起使用正式限值。跨阶段时间序列须拆分或绘制分段限值，不能用一条横线覆盖整个时期。早于实施日的数据会报错，不自动套用现行标准。
- CO 内置单位为 `mg/m3`，其余为 `ug/m3`（亦接受 `μg/m³`）；单位不符会报错，须先换算数据。负值、无穷值拒绝映射，`None`/`NaN` 为缺失。IAQI 配色助手对浓度按 GB/T 8170 修约后映射并向上取整；按 HJ 633—2026，SO₂ 小时值超过 800 μg/m³ 时 IAQI 按 200 计，O₃ 8 小时值超过 800 μg/m³ 时按 300 计，不能随意归为最高等级。
- 内置助手不替代数据完整性、采样有效性、参比状态及统计口径检查。小时 PM 浓度在 2026 版可以映射实时 IAQI，但 GB 3095 未因此产生 PM 小时达标限值。水、土壤、噪声、排放及地方标准须先核实相应版本和适用条件，不能套用环境空气限值或 AQI 色阶。

### 风向箭头绘制

- 气象风向为风的“来向”，以正北为 0°，顺时针增加：90° 东风、180° 南风、270° 西风。输送箭头表示气流“去向”：北风箭头向下，东风向左，南风向上，西风向右。图例或图注明确“箭头指向气流去向”。风玫瑰扇区表示来向，不应随箭头规则翻转扇区。
- 气象来向角 θ 转换为东向/北向分量：`u = -speed * sin(radians(θ))`、`v = -speed * cos(radians(θ))`。数学去向角以正东为 0°、逆时针增加，使用 `u = speed*cos(θ)`、`v = speed*sin(θ)`。必须确认输入约定，不根据字段名猜测；已提供 `east_u/north_v` 时不重复反向。角度统一到 `[0, 360)`，不把风向角直接做普通算术平均。
- **仅表示方向的箭头**：使用真实角度旋转的细长等长箭头，默认长度约 18 pt、线宽约 0.7 pt。可使用 `DrawingArea` + `FancyArrowPatch` + `AnnotationBbox`，在点坐标中绘制箭头，在图上锚定位置；中心两端为 `(cx ± L*u/(2*speed), cy ± L*v/(2*speed))`。箭头大小与风速、时间跨度、y 轴范围无关，不使用八方向文字箭头字符替代真实角度。时序方向箭头排列在固定水平行（如 y=0.95 的 axes 坐标），密集时按统一间隔抽稀，不能靠缩短箭头表示缺测。
- **同时表示风速的矢量箭头**：使用真实 `u/v` 分量，箭头方向与长度分别表达去向和风速；时间轴和浓度轴单位不一致时使用 `quiver(..., angles='uv', ...)` 保持屏幕中的真实方向，固定缩放规则，并添加带 `m/s` 单位的 `quiverkey`。不得把风速矢量和等长方向箭头混用而不说明长度含义。现有业务模板的固定缩放口径由业务工具负责。
- `angles='xy'` 适用于坐标与分量具有一致空间含义的矢量场；需要正确长宽比或投影转换，不能直接把 `m/s` 分量当作经纬度增量。地图箭头必须考虑投影和局地北向，不能无条件将屏幕上方视为正北。图中标明坐标方向或提供必要的方位说明。
- 静风不能凭角度画出确定方向：按数据来源的静风判据显示空心圆/“静风”标记并解释；无静风判据时至少将零风速视为无定义方向。缺失/无效方向不画箭头，缺失与静风分开表示。不擅自用最近方向填补缺失，风速不得为负。
- 常规输送箭头的箭头尖指向运动方向；气象风羽采用另一套来向与风速符号惯例，须明确说明，不能仅改变箭头头部假装成标准风羽。
- 风场污染物叠加时序必须调用 `create_business_chart(chart_type='wind_timeseries', ...)`；气象五要素时序必须调用 `create_business_chart(chart_type='weather_timeseries', ...)`。上述 Python 方法用于业务工具尚未覆盖的自定义图，不用于重新实现现成模板。
- 交付前核对四个基本方向、任意斜向、静风、缺失及抽稀情况；改变画布比例和坐标范围后检查箭头角度与长度含义是否保持一致。

风向定义参考 [NOAA 风向术语](https://forecast.weather.gov/glossary.php?word=wind+direction)；绘图坐标与长度参数参考 [Matplotlib Quiver](https://matplotlib.org/stable/api/_as_gen/matplotlib.quiver.Quiver.html)。

### 数据表达与交付检查

- 缺失不填零，时间缺测保留断线；插值须明确说明。预测与实测用不同线型/符号，预测不确定性用区间表示，不能伪装成监测值。
- 轴标签带单位，图注说明时间范围、平均时间、数据来源及有效样本口径。可比图保持等级断点、系列色和坐标范围一致；柱状图通常从零起，截断坐标须说明。
- 超限点可适度突出；图例必须解释其判据。风向明确气象“来向”口径，不把风向角当作普通线性均值。相关不代表因果，不从颜色推断源贡献。
- 保存前检查标准线、图例、色标、中文和图注是否完整可读。调用助手是便利方式；使用自定义 Python 代码时也必须遵守上述规则。

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot(dates, pm25_daily, label='PM2.5 日均浓度')
ax.set_ylabel('PM2.5 (μg/m³)')
ax.set_xlabel('日期')
add_standard_limit(
    ax, pollutant='PM2.5', average_time='24h', data_average_time='24h',
    grade=2, observed_on='2026-05-01', unit='ug/m3',
)
legend_below(ax, ncols=1)
save_chart(fig, 'pm25-daily.png')
```

等级色和断点依据 [HJ 633—2026](https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/jcffbz/202602/W020260225366493492011.pdf)；限值和过渡安排依据 [GB 3095—2026](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202602/W020260224700452407278.pdf)。官方来源随配置表保存，新增或修订配置须核对原文并更新边界测试。

## matplotlib 图片保存

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
ax.set_title("指标变化趋势")
ax.set_xlabel("日期")
ax.set_ylabel("浓度 (ug/m$^3$)")
ax.grid(axis="y")
save_chart(fig, "trend_chart.png")
```

## 图表组织规则

- 默认一个独立图表一个图片文件；同一主题下的趋势、分布、排名和相关性等分别保存。主题相同不构成合图理由。
- Agent 可按分析问题自主选择图型；一次 Python 调用可以创建多个 Figure 并分别调用 `save_chart`，无需为了减少工具调用而拼接图片。
- 先明确每个分析问题和证据，再选择图表；不要为了增加图表数量重复表达同一结论。
- 仅当共享坐标、同步时间轴或联合阅读对比较有实际必要，或用户明确要求组合图时，才采用分面或多子图；站点、时段或情景对比不自动意味着必须合图。独立图表分别保存，例如 `trend_pm25.png`、`ranking_city.png`。
- 允许的多子图仍须在报告最终插入尺寸下满足上述字号与可读性要求；无法满足时拆图，不能用缩小字号容纳更多内容。业务图表工具已有明确文档的专用组合布局遵循其模板。
- 单个坐标轴中的多条折线、多组柱或多系列散点用于对比是允许的；这属于一个图表，不属于多图拼接。

## Excel 规则

- 修改现有 Excel 时优先用 `openpyxl`，避免 `pandas.to_excel()` 覆盖导致图表和格式丢失。
- 创建新文件可用 `pandas` 或 `openpyxl`。
- 公式优先保留为公式，不要硬编码可计算结果。
- 会商文件合并、图表保留等项目约定，以对应技能文档为准。

## 常见错误

- JSON/数据库读取的数值可能是字符串，计算前显式 `float()` 或 `int()`。
- 字典字段可能缺失，使用 `.get()` 并处理默认值。
- 使用变量前检查 `None`。
- 超时默认 30 秒，复杂任务应拆分或提高 `timeout`。

## pandas dtype 陷阱

- **布尔列取反报错**（`TypeError: bad operand type for unary ~`）：整行赋值 `df.loc[i] = dict` 或合并时混入 `None`/`NaN`，会把 bool 列上转型为 object/float，此后 `~df['col']` 失败。预防：布尔标志列赋值后固定 `df['col'] = df['col'].astype(bool)`（有缺失时先 `fillna(False)`），或干脆改用 0/1 整数列；取反/计数用 `df['col'].eq(False)` 等比较写法替代 `~`。
- **NaN 转整数报错**（`ValueError: cannot convert float NaN to integer`）：含缺失值的数值列不能用 `int()`/`astype(int)`。预防：转整数一律用可空整型 `df['col'].astype('Int64')`；单个值先判空 `int(v) if pd.notna(v) else None`。
- **输入文件未挂载**（`RuntimeError: 未找到会话数据文件`）：`load_data()` 只能读取本次调用 `input_files` 参数中声明的文件，挂载不跨调用保留；每次调用都需重新声明全部要读的路径。

## 一次性 DOCX 最小示例

```python
from docx import Document
from app.services.report.government_docx_style import apply_government_report_style, add_government_title

out = "backend/backend_data_registry/report.docx"
doc = Document()
apply_government_report_style(doc)
add_government_title(doc, "报告")
doc.save(out)
print(out)
```
