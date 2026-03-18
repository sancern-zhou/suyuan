"""
模板报告（方案B）Agent化 Prompt 工具
"""
from typing import Dict, Any, List


def build_template_analysis_prompt(template_content: str, time_range: Dict[str, Any]) -> str:
    """
    构建模板分析 + 工具计划生成的 Prompt
    """
    display = (
        time_range.get("display")
        or f"{time_range.get('start', '')}至{time_range.get('end', '')}".strip("至")
        or "指定时间范围"
    )

    # 提取时间范围用于提示词
    start_date = time_range.get('start', '')
    end_date = time_range.get('end', '')
    date_range = f"{start_date}至{end_date}"

    # 提取最大月份用于单月查询
    if start_date and end_date:
        # 提取结束月份
        import re
        end_month_match = re.search(r'(\d{4})-(\d{2})-\d{2}', end_date)
        if end_month_match:
            year, month = end_month_match.groups()
            max_month = f"{year}-{month}-01至{year}-{month}-31"
        else:
            max_month = "9月1日至9月30日"
    else:
        max_month = "9月1日至9月30日"

    return f"""你是一名空气质量报告生成专家。

任务：阅读以下历史报告模板，提取需要的数据指标，并为每一类内容设计查询计划（使用已有工具）。

历史报告模板（Markdown）：
{template_content}

目标时间：{display}

【时间占位符说明】
模板中可能包含以下时间占位符，请根据语义理解并正确替换：
- 【目标时间段】→ 代表完整时间段（如"2025年1-12月"），用于描述整体趋势
- 【目标单月】→ 代表单月（如"12月"），用于描述特定月份的数据
- 【目标年份】→ 代表年份（如"2025年"）

**重要**：这些占位符仅用于文本描述，不会影响数据查询。查询时使用下方的具体时间参数。

【时间维度规则】
模板包含两种时间维度，必须分别查询：
- 【目标月份范围】→ 完整时间段（如1-9月，用"{date_range}"查询）
- 【目标单月】→ 仅最大月份（如9月，用"{max_month}"查询）

【查询时间粒度要求】
所有查询必须明确查询的时间粒度，例如：按月查询、按日查询、按小时查询、按年查询等。
- 对于完整的单月份和跨月份，时间粒度一般为月度
- 对于单年份，时间粒度一般为年度
- 对于非完整的月份或者跨多日的查询，时间粒度一般为日度
- 【强制禁止】除非用户模板中明确要求"小时"数据，否则绝对不要查询小时粒度数据
  * 原因：跨长周期的小时数据量巨大（1年 × 21城市 × 365天 × 24小时 = 约18万条记录），会导致API超时且LLM无法处理
  * ✅ 正确：时间粒度为月度、时间粒度为日度、时间粒度为年度
  * ❌ 错误：时间粒度为小时、的小时浓度数据、查询小时数据
  * 如果模板需要O3数据，只查询 O3_8h（8小时滑动平均）或评价浓度，不要查询O3小时数据

【同环比数据要求】
如果模板中需要查询同比/环比数据，所有查询必须返回**两个时间段数据**：
- 当前期（TimePoint）：如"{date_range}"或"{max_month}"
- 对比期（ContrastTime）：上一年同期
在question中必须明确写出TimePoint和ContrastTime参数。

【可查询字段详细信息】⭐⭐⭐ 重要参考

在生成question时，必须根据模板需求选择正确的字段名称。以下是API支持的标准字段列表：

## 1. 基础污染物字段
- **SO2**: 二氧化硫浓度（μg/m³）
- **NO2**: 二氧化氮浓度（μg/m³）
- **PM2_5**: PM2.5浓度（μg/m³）
- **PM10**: PM10浓度（μg/m³）
- **CO**: 一氧化碳浓度（mg/m³）
- **O3_8h**: 臭氧8小时滑动平均浓度（μg/m³）

## 2. 综合指标字段
- **CompositeIndex**: 综合指数（环境空气质量综合指数）
- **AQI**: 空气质量指数
- **PrimaryPollutant**: 首要污染物

## 3. 统计指标字段
- **FineDays**: 优良天数
- **FineRate**: 优良率（AQI达标率，百分比）
- **OverDays**: 超标天数
- **OverRate**: 超标率（百分比）
- **ValidDays**: 有效天数
- **TotalDays**: 总天数
- **OneLevel**: 优天数（AQI 0-50）
- **TwoLevel**: 良天数（AQI 51-100）
- **ThreeLevel**: 轻度污染天数（AQI 101-150）
- **FourLevel**: 中度污染天数（AQI 151-200）
- **FiveLevel**: 重度污染天数（AQI 201-300）
- **SixLevel**: 严重污染天数（AQI >300）

## 4. 分污染物超标统计字段
- **O3_8h_PrimaryPollutantOverDays**: O3_8H超标天数
- **pM2_5_PrimaryPollutantOverDays**:PM2.5超标天数
- **pM10_PrimaryPollutantOverDays**:PM10超标天数

## 5. 排名指标字段（排名字段要单独查询）
- **Rank**: 综合排名
- **ComprehensiveRank**: 综合指数排名
- **PM25Rank**: PM2.5浓度排名

## 6. 对比查询特殊字段（同比/环比）
当查询包含对比期时，API会自动返回以下后缀字段：
- **_Compare后缀**: 对比期数值（如: SO2_Compare, PM2_5_Compare, FineRate_Compare）
- **_Increase后缀**: 变化幅度（如: SO2_Increase, PM2_5_Increase, CompositeIndex_Increase）
- **_Rank后缀**: 排名信息（如: SO2_Rank, PM2_5_Rank）

**重要提示**：
1. 字段名称区分大小写，必须使用正确的驼峰命名（如PM2_5，不是pm2.5或PM2.5）
2. 在question中列出字段时，使用中文描述（如"PM2.5浓度"），API会自动映射到对应字段
3. 如果需要同比数据，必须在question中明确要求"返回同比变化"，API才会返回_Compare和_Increase字段
4. 综合统计报表、对比分析报表必须包含PollutantCode字段选择

**字段选择示例**：
✅ 正确："查询广东省2025年各城市的AQI达标率（FineRate）、PM2.5浓度、O3评价浓度、超标天数（OverDays）、综合指数（CompositeIndex）、综合排名（Rank）"
✅ 正确："查询并返回PM2.5同比变化（PM2_5_Compare、PM2_5_Increase）、优良率同比变化（FineRate_Compare、FineRate_Increase）"
❌ 错误："查询空气质量数据"（字段不明确）

【可用工具及适用场景】

【工具选择优先级规则】⭐⭐⭐
1. **优先使用 `get_guangdong_regular_stations`**：查询广东省各城市/站点的空气质量数据（城市排名、区域对比等）
2. **最后使用 `get_air_quality`**：仅当以下情况才调用：
   - 查询的城市不属于广东省（如北京、上海、武汉等）
   - `get_guangdong_regular_stations` 查询失败或无返回数据

【工具适用场景】
- `get_guangdong_regular_stations`：广东省区域对比（城市排名、区域对比、时序对比）
- `get_component_data`：涉及"组分 / 成分 / 源解析"等内容时，用于查询 PM2.5/VOCs 等组分数据
- `get_weather_data`：**暂时不使用**。即使模板中提到气象条件（温度、湿度、风速、日照、降水等），也**不要生成气象数据查询需求**，跳过相关章节的数据查询


【输出格式要求】
请输出 JSON（不要添加其他解释）：
{{
  "data_requirements": [
    {{
      "section": "章节标题（例如：总体状况、城市状况、附表1-目标期等）",
      "tool": "get_jining_regular_stations | get_guangdong_regular_stations | get_component_data",
      "question": "完整自然语言问题，包含城市/区域、目标时间范围、指标名称、时间粒度（日/月等），以及是否需要同比/环比/对比",
      "query_type": "province_overview | city_ranking | city_detail_table | general"
    }}
  ]
}}

**注意**：不要使用 `get_weather_data` 工具，暂时跳过所有气象数据查询需求。

【question 编写要求】

1. **时间范围选择**：
   - 【目标月份范围】→ 用完整时间范围（如"{date_range}"）
   - 【目标单月】→ 用单月时间范围（如"{max_month}"）

2. **同比数据格式（必须明确）**：
   ✅ 正确："...TimePoint=xxx，ContrastTime=xxx..."
   ❌ 错误："...并与上一年同期进行同比分析" (模糊表达)

3. **多指标合并（强制）**：
   - 工具支持一次查询多个指标
   - **禁止**将同一时间段、同一地点的多个指标拆分为多条查询

4. **字段完整性要求（强制）**
   在生成每个查询question之前，必须完成以下步骤：

   a) **分析模板需求**：仔细阅读模板对应章节，列出该章节需要的所有数据字段
      例如：AQI达标率（FineRate）、PM2.5浓度、PM2.5同比变化、O3评价浓度（O3_8h）、O3同比变化、超标天数（OverDays）、综合指数（CompositeIndex）等

      **参考上方【可查询字段详细信息】章节，确保使用正确的字段名称，排名信息需要查询对应的字段**

   b) **生成完整question**：确保question中明确列出所有需要的字段，不遗漏任何一个
      ✅ 正确示例：
      "查询广东省2025年1月1日至2025年12月31日各城市空气质量数据（21条记录），包括AQI达标率（FineRate）、PM2.5浓度、O3评价浓度（O3_8h）、超标天数（OverDays），并与2024年同期（2024-01-01至2024-12-31）进行同比分析，返回PM2.5同比变化（PM2_5_Compare、PM2_5_Increase）、O3同比变化（O3_8h_Compare、O3_8h_Increase）、综合指数同比变化（CompositeIndex_Compare、CompositeIndex_Increase）、优良率同比变化（FineRate_Compare、FineRate_Increase）等字段"

      ❌ 错误示例：
      "查询广东省2025年空气质量数据"（字段不明确，会导致多次查询补充）
      "查询广东省2025年AQI、PM2.5数据"（遗漏O3、超标天数、综合指数等字段）
      "查询广东省2025年数据并与2024年对比"（没有明确列出需要对比的字段和_Compare、_Increase后缀）

   c) **一次性查询完整**：同一时间段、同一地区的所有数据必须在一个question中完整列出
      - 禁止分多次查询补充缺失字段（排名字段除外）
      - 禁止先查询部分字段，再查询其他字段
      - 如果模板需要10个字段，question必须明确列出全部10个字段（排名字段除外）
      - 如果需要同比数据，必须明确列出所有需要对比的字段及其_Compare、_Increase后缀

   d) **验证字段覆盖**：生成question后，检查是否覆盖了模板需要的所有字段
      - 如果模板表格有10列，question必须包含对应的10个字段（排名字段除外）
      - 如果模板需要同比数据，question必须明确要求返回同比字段（如PM2_5_Compare、FineRate_Compare、CompositeIndex_Increase）
      - 对照【可查询字段详细信息】章节，确认字段名称正确

5. **数据粒度明确要求（强制）**：⭐⭐⭐
   在question中必须明确指定数据粒度和预期记录数：

   - **年度数据**：明确写"年度汇总数据"或"按年统计"，并说明预期记录数
     ✅ 正确："查询广东省21个城市2025年的年度汇总数据（21条记录），包括全年AQI达标率、PM2.5年均浓度、全年超标天数等"

   - **月度数据**：明确写"月度数据"或"按月统计"，并说明预期记录数
     ✅ 正确："查询广州市2025年1-12月的月度数据（12条记录），包括每月AQI、PM2.5月均值等"
W
   - **日度数据**：明确写"每日数据"或"按日统计"，并说明预期记录数
     ✅ 正确："查询东莞市2025年10月1日-5日的每日数据（5条记录），包括每天的AQI、PM2.5日均值、O3日最大8小时值等"
     ❌ 错误："查询东莞市2025年的日度空气质量数据"（没说明需要5条记录，API可能返回1条聚合数据）

【强制规则】
- 空气质量查询优先顺序：get_jining_regular_stations → get_guangdong_regular_stations → get_air_quality
- 济宁地区用 get_jining_regular_stations
- 广东其他地区用 get_guangdong_regular_stations
- 其他城市或前两者失败时用 get_air_qualityW
- 违反时间维度或同比要求将导致查询失败
- 排名和综合指数排名单独生成查询请求，不要与其他指标合并查询。且排名结果需要直接获取，不能基于数据自己进行排名。
"""


def build_report_generation_prompt(
    template_content: str,
    collected_data: List[Dict[str, Any]],
    time_range: Dict[str, Any]
) -> str:
    """
    构建最终报告生成 Prompt
    """
    display = (
        time_range.get("display")
        or f"{time_range.get('start', '')}至{time_range.get('end', '')}".strip("至")
        or "指定时间范围"
    )

    return f"""你是一名空气质量报告撰写专家。

任务：对比历史报告模板，结合最新获取的数据，生成 {display} 的完整报告（Markdown）。

历史报告模板：
{template_content}

已获取的数据（标准化，含 data_id，可追溯）：
{collected_data}

【核心要求】

1. **严格遵循模板结构**
   - 必须完全按照历史报告模板的结构、标题层级、章节顺序输出
   - 不得添加模板中没有的章节或内容
   - 不得删除模板中的任何章节
   - 保持与模板相同的表述风格和格式

2. **严禁编造数据**
   - **绝对禁止**编造、推测或虚构任何数据
   - **只能使用**上述"已获取的数据"中提供的数据
   - 如果某个数据在"已获取的数据"中不存在，必须明确标注"暂缺"或"数据未获取"
   - 不得使用"大约"、"估计"、"可能"等模糊表述来掩盖数据缺失

3. **数据替换原则**
   - 用最新数据替换模板中的旧数据
   - 保持数据的准确性和一致性
   - **同比/环比计算**：
     * 如果已获取的数据中包含当前期和对比期的数据，必须计算同比/环比变化
     * 同比变化 = (当前期数据 - 去年同期数据) / 去年同期数据 × 100%
     * 环比变化 = (当前期数据 - 上一期数据) / 上一期数据 × 100%
     * 在报告中明确标注变化方向和幅度（如"同比上升9.5%"、"同比下降2.7个百分点"）
   - 城市排名/表格必须严格按照实际数据排序和填写

4. **数据缺失处理**
   - 如果某个指标的数据未获取到，在对应位置明确标注"暂缺"或"数据未获取"
   - 不得用其他数据替代或编造数据填充
   - 不得跳过该部分，必须保留模板中的结构

5. **输出格式**
   - 输出完整的 Markdown 文本
   - 尽量保持与模板相同的结构（标题、列表等）（除了表格型内容（附表1、附表2等），输入的表格格式可能是乱的，必须用标准 Markdown 表格语法来呈现）
   - 确保所有数据引用准确，可追溯
   - **移除所有图表占位符**：模板中可能包含 `[INSERT_CHART:xxx]` 或类似的图表占位符，请在生成报告时**完全移除这些占位符**，不要保留在最终输出中

【表格型内容输出要求】
1. 如果模板中某一部分在语义上是表格（即使在当前 Markdown 中只是多行文字和数字），请在生成新报告时，必须用**标准 Markdown 表格语法**来呈现：
   - 使用 `| 列名1 | 列名2 | ... |` + `| --- | --- |` 的形式定义表头；
   - 每一行对应一个城市或区域，单元格用 `|` 分隔。
2. 如果某些单元格数据缺失，请在表格中写明"暂缺"或"数据未获取"，而不是删除该列或该行。

【重要提醒】
- 你的任务是**严格按照模板结构，用真实数据替换旧数据**，而不是创作新报告
- 如果数据不足，宁可标注"暂缺"，也绝不能编造数据
- 报告的结构和内容必须与模板保持一致（除了表格型内容（附表1、附表2等），输入的表格格式可能是乱的，必须用标准 Markdown 表格语法来呈现）
"""
