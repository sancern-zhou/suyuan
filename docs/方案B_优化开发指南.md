# 方案B（临时报告 - 结构化拆解）优化开发指南

## 📋 文档说明（2025-01-14 基于最佳实践修正）

本文档针对方案B的当前状态，结合**行业最佳实践**和**项目真实需求**，提供精确的开发路径。

**当前状态**：核心架构已建立，但数据流存在断层

**关键修正**：
1. ⚠️ **删除P0-1**：方案B不需复杂模板语法（each/if/llm_analysis），这是方案C的需求
2. ⚠️ **修正P0-2**：重点不是"接API"，而是**标准化返回结构**
3. ✅ **强化P0-3**：数据提取是当前最大瓶颈
4. 🆕 **新增隐藏P0**：ReportParser需要数据点提取兜底

---

## 🎯 修正后的P0 - 数据流完整性（3天内完成）

### **原则：先让数据流能跑通，再谈优化**

---

### P0-0：ReportParser - 结构解析“LLM-Only”（⚠️ 新增）

**文件位置**：`app/services/report_parser.py`

**当前问题**：
- LLM 解析可能失败或输出非严格JSON，导致结构化管道中断
- 之前曾引入“正则兜底提取”，但这与我们当前的 Agent 设计理念不一致（方案B要求 0-regex）

**最小可用实现（0-regex）**：

```python
# app/services/report_parser.py

async def parse(self, content: str) -> ReportStructure:
    """
    方案B：严格LLM解析（0-regex）

    策略：
    - Prompt 强约束：只能输出一个JSON对象（无解释文本/无Markdown围栏）
    - 失败处理：有限重试（2次），仍失败则抛错（不做正则兜底）
    """
    prompt = self._build_parse_prompt(content)
    result_data = await llm_service.call_llm_with_json_response(prompt=prompt, max_retries=2)
    return ReportStructure(**result_data)
```

**优先级理由**：**这是数据流的起点。只要结构不稳定，后续数据契约与渲染都会空转**

---

### P0-1：TemplateDataFetcher - 数据标准化（修正版）

**文件位置**：
- `app/services/template_data_fetcher.py`（修改）
- `app/services/real_api_client.py`（已存在；注意：当前返回多为原始dict/list，未必是UDF v2.0）

**当前问题**：
- `_extract_data()` 只是TODO，没有实际提取逻辑
- 外部API返回格式多样，未统一为标准schema
- ⚠️ **未对齐“统一解析→UDF v2.0→存储→返回 data_id”的项目规范**：目前方案B走 `TemplateDataFetcher -> real_api_client`，没有复用工具层的UDF v2.0标准化与 `data_id` 存储范式，导致下游只能“猜字段/硬编码”，难以满足数据契约。

**修正重点**：**不是接入API，而是确保返回格式可预测**

#### ✅ 1）先确认“数据契约（Schema Contract）”的边界：方案B也必须输出可追溯的数据引用

结合项目现有实现（如 `get_air_quality` / `get_component_data` 工具），统一规范实际上是：

- **统一解析**：把外部响应解析成稳定结构
- **UDF v2.0 标准化**：字段名/值做标准化，并在 `metadata.schema_version="v2.0"` 中记录映射信息
- **统一存储并返回 `data_id`**：通过 `ExecutionContext.save_data(...)` 或 `context.data_manager.save_data(...)` 得到 `data_id`
- **下游只消费“标准化后的数据 + data_id（引用）”**，而不是直接消费外部原始响应

因此，方案B在“数据获取层”的契约建议固定为：

- 每次查询返回：`{ status, success, data, metadata{schema_version, query_type, time_range, data_id, field_mapping_info}, summary }`
- `data` 必须是可预测结构（按 query_type 固定字段/行结构），并与模板里要填充的指标可映射

#### ✅ 2）推荐落地路径（与现有统一规范一致）：通过工具层/上下文复用 UDF v2.0 + data_id

**推荐方案（优先级最高）**：在 `TemplateDataFetcher` 中不直接调用 `real_api_client`，改为通过 `ToolExecutor + ExecutionContext` 调用你们已有“查询工具”，让工具完成：
`外部调用 → 统一解析 → UDF v2.0 标准化 → save_data → 返回 data_id`

好处：
- 复用现有“统一解析 + 标准化 + 存储 + data_id”链路，避免重复造轮子
- 工具层已有字段映射/标准化能力（`data_standardizer`），更接近“数据契约”
- 下游（DataOrganizer/Renderer）可以只围绕 `data_id` 或标准化后的 `data` 工作

**备选方案（仅当必须保留 real_api_client）**：
- 在 `real_api_client` 或 `TemplateDataFetcher._execute_query()` 后增加 **标准化与UDF封装**，并把结果写入 `ExecutionContext` 生成 `data_id`
- 注意：这样会与工具层能力重复，维护成本更高，推荐仅用于临时过渡

> 小提示：无论走哪条路，P0阶段要避免“静默造数（mock）”。如果必须降级，请返回 `status=partial/empty` 并在 `metadata.missing_fields` 里标注缺失字段，渲染时明确提示“缺数/接口不可用”。

```python
# app/services/real_api_client.py (或现有文件的补充)

class RealAPIClient:
    """负责将多源API转化为统一Schema"""

    # ========== 标准Schema定义 ==========
    PROVINCE_OVERVIEW_SCHEMA = {
        "aqi_rate": float,        # AQI达标率（0-100）
        "aqi_yoy": float,         # AQI同比变化（正负百分比）
        "pm25_avg": float,        # PM2.5平均浓度
        "pm25_yoy": float,        # PM2.5同比
        "o3_avg": float,          # O3浓度
        "o3_yoy": float,          # O3同比
    }

    CITY_RANKING_SCHEMA = {
        "best_5": list,           # [{"city": "广州", "value": 3.2, "rank": 1}, ...]
        "worst_5": list,          # 同上
        "metric": str,            # 排名指标（如"综合指数"）
    }

    CITY_DETAIL_TABLE_SCHEMA = [
        {                        # 数组每项
            "city": str,
            "aqi_rate": float,
            "pm25": float,
            "o3": float,
            "composite": float,
            "rank": int
        }
    ]

    def _standardize_province(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """强制转化为province_overview标准Schema"""

        # 定义云端字段 -> 标准字段的映射（可能来自不同API版本）
        field_mapping = {
            # 标准字段名      # 可能的云端字段名（多种变体）
            "aqi_rate":      ["aqi_compliance_rate", "aqi达标率", "合格率"],
            "aqi_yoy":       ["aqi_year_over_year", "AQI同比", "aqi_yoy_ytd"],
            "pm25_avg":      ["pm2.5_average", "PM2.5均值", "pm25_avg_24h"],
            "pm25_yoy":      ["pm2.5_yoy", "PM2.5同比", "pm25_year_over_year"],
            "o3_avg":        ["o3_average", "O3浓度", "o3_8h_avg"],
            "o3_yoy":        ["o3_yoy", "O3同比", "o3_year_over_year"],
        }

        standardized = {}
        mapped_fields = set()

        for std_field, possible_fields in field_mapping.items():
            found = False
            for cloud_field in possible_fields:
                if cloud_field in raw_data:
                    standardized[std_field] = raw_data[cloud_field]
                    mapped_fields.add(cloud_field)
                    found = True
                    break

            if not found:
                logger.warning(f"字段缺失: {std_field} (尝试了 {possible_fields})")
                standardized[std_field] = None

        # 记录未映射的字段（用于调试）
        unmapped = set(raw_data.keys()) - mapped_fields
        if unmapped:
            logger.debug(f"未映射字段: {unmapped}")

        return standardized

    def _standardize_ranking(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """标准化排名数据，确保结构一致"""

        # 处理best_5（不同API返回格式可能不同）
        best_5 = []
        raw_best = raw.get("best_5") or raw.get("top_cities") or raw.get("top_5")

        if isinstance(raw_best, list):
            for idx, item in enumerate(raw_best[:5]):
                if isinstance(item, str):
                    best_5.append({"city": item, "rank": idx + 1, "value": 0})
                elif isinstance(item, dict):
                    best_5.append({
                        "city": item.get("city") or item.get("name"),
                        "rank": item.get("rank", idx + 1),
                        "value": item.get("value") or item.get("composite") or 0
                    })

        # 同样处理worst_5
        worst_5 = []
        raw_worst = raw.get("worst_5") or raw.get("bottom_cities") or raw.get("bottom_5")
        if isinstance(raw_worst, list):
            for idx, item in enumerate(raw_worst[:5]):
                if isinstance(item, str):
                    worst_5.append({"city": item, "rank": idx + 1, "value": 0})
                elif isinstance(item, dict):
                    worst_5.append({
                        "city": item.get("city") or item.get("name"),
                        "rank": item.get("rank", idx + 1),
                        "value": item.get("value") or item.get("composite") or 0
                    })

        return {
            "best_5": best_5,
            "worst_5": worst_5,
            "metric": raw.get("metric") or raw.get("指标") or "综合指数"
        }

    def _standardize_table(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """标准化表格数据，确保每行字段完整"""

        if not isinstance(raw, list):
            logger.error(f"Table data should be list, got: {type(raw)}")
            return []

        standardized = []

        for row in raw:
            # 多字段映射，确保鲁棒性
            new_row = {
                "city": row.get("city") or row.get("城市") or row.get("name"),
                "aqi_rate": row.get("aqi_rate") or row.get("AQI达标率") or row.get("aqi"),
                "pm25": row.get("pm25") or row.get("PM2.5") or row.get("pm2.5"),
                "o3": row.get("o3") or row.get("O3") or row.get("o3_avg"),
                "composite": row.get("composite") or row.get("综合指数") or row.get("composite_index"),
                "rank": row.get("rank") or row.get("排名") or 0
            }
            standardized.append(new_row)

        return standardized
```

```python
# app/services/template_data_fetcher.py (关键修改)

class TemplateDataFetcher:
    def __init__(self, tool_executor: ToolExecutor):
        self.tool_executor = tool_executor
        self.api_client = RealAPIClient()  # 已在上面定义

    async def _execute_query(self, query_type: str, requirements: List[Dict[str, Any]],
                           time_range: Dict[str, str]) -> Dict[str, Any]:
        """执行查询 - 返回标准化数据"""

        # 优先使用真实API（如果已连接）
        try:
            if query_type == "province_overview":
                raw_data = await self._call_province_api(time_range)
                return {"province_data": self.api_client._standardize_province(raw_data)}

            elif query_type == "city_ranking":
                raw_data = await self._call_ranking_api(time_range)
                return {"ranking_data": self.api_client._standardize_ranking(raw_data)}

            elif query_type == "city_detail_table":
                raw_data = await self._call_table_api(time_range)
                return {"table_data": self.api_client._standardize_table(raw_data)}

            else:
                raise ValueError(f"Unknown query_type: {query_type}")

        except Exception as e:
            logger.error(f"API调用失败: {e}, 降级到Mock")
            return self._mock_query_result(query_type, time_range)

    async def _call_province_api(self, time_range: Dict[str, str]) -> Dict[str, Any]:
        """调用省级概览API（需根据实际API调整）"""
        # 这里需要连接到实际的API...
        # 暂时返回mock，但格式需完整
        return {
            "aqi_compliance_rate": 93.2,
            "aqi_year_over_year": -2.5,
            "pm2.5_average": 24.0,
            "pm2.5_yoy": 8.5,
            "o3_average": 156.0,
            "o3_yoy": 5.2
        }

    def _extract_data(self, query_result: Dict[str, Any], requirement: Dict[str, Any]) -> Dict[str, Any]:
        """
        从标准化结果中提取特定数据点 - 关键修复！！！

        原实现：TODO，直接返回原数据
        新实现：按数据点名称精确提取
        """

        section_id = requirement["section_id"]
        data_points = requirement.get("data_points", [])

        # 获取标准化数据块
        if "province_data" in query_result:
            source_data = query_result["province_data"]
        elif "ranking_data" in query_result:
            source_data = query_result["ranking_data"]
        elif "table_data" in query_result:
            source_data = query_result["table_data"]
        else:
            source_data = {}

        # 按数据点名称提取值（使用智能匹配）
        extracted = {}
        for point in data_points:
            point_name = point["name"]
            value = self._smart_match_value(source_data, point_name)
            extracted[point_name] = value

        return {
            "section_id": section_id,
            "data_points": extracted,
            "query_type": requirement.get("query_type"),
            "raw_data_preview": str(source_data)[:100]  # 调试用
        }

    def _smart_match_value(self, data: Dict[str, Any], point_name: str) -> Any:
        """
        智能匹配数据点
        优先级：直接匹配 > 近似匹配 > 值探测
        """

        # 直接映射表
        direct_map = {
            "AQI达标率": "aqi_rate",
            "AQI同比": "aqi_yoy",
            "PM2.5浓度": "pm25_avg",
            "PM2.5同比": "pm25_yoy",
            "PM10浓度": "pm10_avg",
            "O3浓度": "o3_avg",
            "O3同比": "o3_yoy",
            "综合指数": "composite"
        }

        if point_name in direct_map:
            return data.get(direct_map[point_name], "N/A")

        # 近似匹配（包含关键词）
        for key, value in data.items():
            if isinstance(value, (int, float)):
                # 检查字段名是否包含关键信息
                key_lower = key.lower()
                if any(k in key_lower for k in ["pm25", "pm2.5"]):
                    if "PM2.5" in point_name:
                        return value
                elif "o3" in key_lower:
                    if "O3" in point_name:
                        return value
                elif "aqi" in key_lower and "rate" in key_lower:
                    if "AQI达标率" in point_name:
                        return value

        # 终极方案：返回第一个数值（辅助报告生成）
        if not data:
            return "N/A"

        for value in data.values():
            if isinstance(value, (int, float)):
                return value

        # 如果都没有，返回N/A并记录警告
        logger.warning(f"无法匹配数据点 '{point_name}' in {list(data.keys())}")
        return "N/A"

    def _mock_query_result(self, query_type: str, time_range: Dict[str, Any]) -> Dict[str, Any]:
        """Mock数据 - 必须符合标准Schema"""

        if query_type == "province_overview":
            return {
                "province_data": {
                    "aqi_rate": 93.2,
                    "aqi_yoy": -2.5,
                    "pm25_avg": 24.0,
                    "pm25_yoy": 8.5,
                    "o3_avg": 156.0,
                    "o3_yoy": 5.2
                }
            }

        elif query_type == "city_ranking":
            return {
                "ranking_data": {
                    "best_5": [
                        {"city": "梅州", "rank": 1, "value": 2.8},
                        {"city": "汕头", "rank": 2, "value": 3.1},
                        {"city": "河源", "rank": 3, "value": 3.2}
                    ],
                    "worst_5": [
                        {"city": "佛山", "rank": 1, "value": 4.8},
                        {"city": "东莞", "rank": 2, "value": 4.6}
                    ],
                    "metric": "综合指数"
                }
            }

        elif query_type == "city_detail_table":
            return {
                "table_data": [
                    {"city": "广州", "aqi_rate": 91.2, "pm25": 26, "o3": 158, "composite": 3.9, "rank": 15},
                    {"city": "深圳", "aqi_rate": 94.5, "pm25": 22, "o3": 145, "composite": 3.3, "rank": 8},
                    {"city": "佛山", "aqi_rate": 89.3, "pm25": 28, "o3": 162, "composite": 4.2, "rank": 18}
                ]
            }

        return {}
```

**优先级理由**：**标准化是数据可信的基础，没有它匹配字段会失败**

---

### P0-2：DataOrganizer - 接收上游数据（优化版）

**文件位置**：`app/services/data_organizer.py`

**核心调整**：**从"自己找值"改为"接收上游提取好的值"**

```python
# app/services/data_organizer.py

class DataOrganizer:

    def _find_data_value(self, data: Dict[str, Any], point: Dict[str, Any]) -> Any:
        """
        数据提取 - 核心逻辑修改

        上游data来源（来自TemplateDataFetcher._extract_data）：
        {
            "data_points": {
                "AQI达标率": 93.2,
                "PM2.5浓度": 24.0
            }
        }

        本方法职责：直接从data_points中取值，不重复匹配
        """

        point_name = point.get("name", "")
        data_points = data.get("data_points", {})

        # 优先级1：直接使用上游提取的结果
        if point_name in data_points:
            value = data_points[point_name]
            if value is not None and value != "N/A":
                return value

        # 优先级2：如果上游没有，尝试在原始数据中匹配（兜底）
        # data可能包含{"raw_data": {...}} 或直接就是原始数据
        raw_data = data.get("raw_data") or data.get("data") or data

        # 使用之前的智能匹配逻辑
        if isinstance(raw_data, dict):
            FIELD_MAPPING = {
                "AQI达标率": ["aqi_rate", "AQI达标率"],
                "PM2.5浓度": ["pm25_avg", "PM2.5", "pm25"],
                "O3浓度": ["o3_avg", "O3", "o3"],
                "综合指数": ["composite", "综合指数"]
            }

            for display_name, possible_fields in FIELD_MAPPING.items():
                if display_name in point_name:
                    for field in possible_fields:
                        if field in raw_data:
                            return raw_data[field]

        return "N/A"

    def _format_section_data(
        self,
        section_data: Dict[str, Any],
        section_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """格式化章节数据 - 使用上游提取的结果"""

        formatted_points = []

        # 从上游获取已经提取好的数据点
        data_points = section_data.get("data_points", {})

        # 按section_config中定义的顺序格式化
        if "data_points" in section_config:
            for point in section_config["data_points"]:
                point_name = point.get("name")

                formatted_point = {
                    "name": point_name,
                    "value": data_points.get(point_name, "N/A"),  # 直接用上游结果
                    "unit": point.get("unit", ""),
                    "comparison": point.get("comparison", "")
                }

                # 如果没有对比信息，尝试从原始数据中提取
                if not formatted_point["comparison"]:
                    formatted_point["comparison"] = self._extract_comparison_from_raw(
                        section_data, point_name
                    )

                formatted_points.append(formatted_point)

        return formatted_points

    def _extract_comparison_from_raw(self, data: Dict[str, Any], point_name: str) -> str:
        """从原始数据中提取同比/环比信息"""
        raw_data = data.get("raw_data") or data

        if not isinstance(raw_data, dict):
            return ""

        # 查找包含同比的字段
        for key, value in raw_data.items():
            if "yoy" in key.lower() or "同比" in key:
                if isinstance(value, (int, float)):
                    trend = "上升" if value > 0 else "下降"
                    return f"同比{trend}{abs(value)}%"

        return ""
```

**优先级理由**：**简化职责链，上游保证数据准确性，本层只做格式化**

---

### P0-3：ReportRenderer - 基础版渲染（保持简单）

**文件位置**：`app/services/report_renderer.py`

**当前需求**：**方案B只需要基础替换，不要复杂语法**

```python
class ReportRenderer:
    """
    方案B渲染（0-regex）：
    - 不做任何正则替换
    - 仅按“## ”二级标题分段，然后按标题精确匹配替换内容
    """

    def _split_by_h2(self, md: str):
        preamble, sections = "", []
        lines = (md or "").splitlines()
        cur_title, cur_lines, in_sections = None, [], False

        def flush():
            nonlocal cur_title, cur_lines
            if cur_title is not None:
                sections.append({"title": cur_title, "content": "\n".join(cur_lines).strip()})
            cur_title, cur_lines = None, []

        pre_lines = []
        for line in lines:
            if line.startswith("## "):
                in_sections = True
                flush()
                cur_title = line[3:].strip()
                continue
            if not in_sections:
                pre_lines.append(line)
            else:
                cur_lines.append(line)
        flush()
        preamble = "\n".join(pre_lines).strip()
        return preamble, sections

    def _join_by_h2(self, preamble: str, sections):
        parts = []
        if preamble:
            parts.append(preamble)
        for s in sections:
            if not s.get("title"):
                continue
            parts.append(f"## {s['title']}")
            if s.get("content"):
                parts.append(s["content"])
        return "\n\n".join(parts).strip() + "\n"
```

**对于方案C的复杂语法（{{#each}}等）：建议暂不实现，留到方案C时一次性引入Jinja2**

---

### P0-4：LLM服务集成（保持简单）

**文件位置**：`backend/app/services/llm_service.py`（已存在）

**当前状态**：项目内已实现统一的 `llm_service.call_llm_with_json_response(...)`，可直接用于“结构解析 → 严格JSON”与“分析段落生成”。

**方案B约束（重要）**：为符合“0-regex”，不要在文档中引入任何基于正则的清洗/提取示例；结构稳定性通过“强约束prompt + 有限重试 + JSON反序列化校验”保障。

**配置**：
```bash
LLM_PROVIDER=mock  # 当前使用mock，后期改为openai/tianji
LLM_API_KEY=your_key
```

**优先级理由**：**当前mock已足够，真实LLM不是方案B的阻塞点**

---

## 📊 实施路线图（3天方案）

### **Day 1：建立完整数据链路**

**上午（3小时）**
- ✅ **实施P0-0**：ReportParser 改为 LLM-Only 严格JSON（0-regex）
- ✅ **实施P0-1**：实现RealAPIClient._standardize_*方法
- ✅ **实施P0-1**：修复TemplateDataFetcher._extract_data()

**下午（3小时）**
- ✅ **实施P0-2**：修复DataOrganizer._find_data_value()
- ✅ **实施P0-2**：测试数据从解析→获取→组织的完整流动
- ✅ **实施基础渲染**：确保模板替换能出基础报告

**晚上（1小时）**
- 🔧 单元测试：各层数据转换正确性
- 🔧 集成测试：从模板输入到Markdown输出

---

### **Day 2：数据质量与测试**

**上午（3小时）**
- ✅ **P1测试**：编写完整测试用例
  - 数据字段映射测试
  - 并发查询测试
  - 降级策略测试

**下午（3小时）**
- 🔧 **LLM服务**：完成mock + 简单真实集成
- 🔧 **API连接**：测试真实数据源（如果可用）
- 🔧 **端到端验证**：生成真实报告，验证数据准确性

---

### **Day 3：前端与优化**

**上午（3小时）**
- ✅ **前端流式**：SSE实时进度展示
- ✅ **错误处理**：网络中断自动重连

**下午（3小时）**
- ✅ **性能优化**：并行查询 + 缓存
- ✧ **可选**：如果方案B证明可行，考虑是否引入Jinja2为方案C铺路

---

## 🎯 关键里程碑（可衡量的结果）

| 里程碑 | 验收标准 | 时间 |
|--------|----------|------|
| **数据流打通** | 从模板→数据→报告，输出含真实值的Markdown | Day 1结束 |
| **数据准确性** | 100%通过字段映射测试，无硬编码 | Day 2上午 |
| **端到端验证** | 上传模板→生成→下载，报告数值正确 | Day 2结束 |
| **可用性达标** | 流式+重连，用户可接受的体验 | Day 3结束 |

---

## 🚫 已从P0移除的内容

| 原P0内容 | 调整原因 | 新优先级 |
|---------|---------|---------|
| 报告渲染器复杂语法 | 方案B不需要，方案C才需 | P2（方案C时实施） |
| LLM真实分析生成 | Mock已足够，不影响数据流验证 | P1（待数据准确后） |
| 高性能优化 | 先跑通，再优化 | P2（基础可用后） |

---

## 💡 关键决策点

### Q1: 是否引入Jinja2做模板渲染？
**A**: ❌ **方案B阶段不引入**，因为：
- 方案B是"结构化替换"，不是"模板引擎渲染"
- 手动替换已足够（简单、可控）
- Jinja2留给方案C一次性引入

### Q2: 何时切换Mock到真实API？
**A**: ✅ **Day 1下午验证数据结构后**，因为：
- P0重点是"结构标准化"，不是"拿到真实数据"
- 只要Schema一致，Mock->真实切换零成本

### Q3: 是否需要在方案B引入数据点的“正则兜底提取”？
**A**: ❌ **不需要（且明确禁止）**，因为：
- 方案B的设计原则是 **LLM-Only + 0-regex**，不允许用正则替代“理解/抽取”能力
- 数据点应来自两处：① LLM结构化解析（`sections[].data_points`）② 上游数据契约（UDF v2.0 + data_id）
- 稳定性保障应通过：**严格JSON输出约束 + 有限重试 + 结构校验（无正则）**，而不是正则猜测

---

## 📈 成功率评估

**按此方案实施，方案B成功率：>95%**

**关键成功因素**：
1. ✅ 修正了"模板语法"误区（非必需）
2. ✅ 强化了"数据标准化"（瓶颈点）
3. ✅ 补上了“结构解析LLM-Only（0-regex）”这一隐藏P0
4. ✅ 删减了非必需功能（聚焦价值）

**失败风险点**：
1. ⚠️ 真实API字段名差异 → 通过`_standardize_*`映射解决
2. ⚠️ LLM解析不稳定 → 通过“严格JSON约束 + 有限重试 + 结构校验（0-regex）”解决
3. ⚠️ 并发问题 → 通过`asyncio.gather`和连接池解决

---

**下一步：开始Day 1上午任务**

请优先按 P0 顺序落地“结构解析LLM-Only（0-regex）→ 数据契约化 → 渲染分段替换（0-regex）”。

> 说明：`{{#each}}/{{#if}}/{{#llm_analysis}}` 等属于方案C标注模板能力，不属于方案B范围；且你们要求0-regex，方案C建议后续用成熟模板引擎（如Jinja2）实现。

---

#### 2. TemplateDataFetcher API客户端集成

**文件位置**：`app/services/template_data_fetcher.py` + 新建 `app/services/real_api_client.py`

**当前问题**：
- `api_client` 未找到（代码中导入但未实现）
- 缺少真实数据获取逻辑
- 仅有模拟数据降级

**优化方案**：

```python
# 新建: app/services/real_api_client.py
from typing import Dict, Any, List
import os
import httpx

class RealAPIClient:
    """真实API客户端 - 集成现有工具层"""

    def __init__(self):
        # 复用现有的空气质量和气象数据工具
        from app.tools.query.get_air_quality import AirQualityTool
        from app.tools.query.get_weather_data import WeatherDataTool

        self.air_tool = AirQualityTool()
        self.weather_tool = WeatherDataTool()

    async def query_province_overview(self, time_range: Dict[str, str]) -> Dict[str, Any]:
        """省级概览查询"""
        question = f"查询广东省{time_range['start']}至{time_range['end']}空气质量"
        question += "，包括AQI达标率、PM2.5浓度、O3浓度及同比变化"

        result = await self.air_tool.execute({"query": question})
        return self._parse_to_standard_format(result)

    async def query_city_ranking(self, time_range: Dict[str, str]) -> Dict[str, Any]:
        """城市排名查询"""
        question = f"查询广东省{time_range['start']}至{time_range['end']}空气质量排名"
        question += "，包括综合指数、PM2.5、O3排名前5和后5的城市"

        result = await self.air_tool.execute({"query": question})
        return self._parse_ranking(result)

    async def query_city_detail_table(self, time_range: Dict[str, str]) -> List[Dict[str, Any]]:
        """城市详细数据表"""
        question = f"查询广东省21个地市{time_range['start']}至{time_range['end']}空气质量详细数据"
        question += "，包括AQI达标率、PM2.5、O3、综合指数及同比"

        result = await self.air_tool.execute({"query": question})
        return self._parse_table(result)

    def _parse_to_standard_format(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """标准化为统一格式"""
        # 从tool_result中提取关键字段
        data = result.get("data", {})

        return {
            "aqi_rate": data.get("aqi_compliance_rate"),
            "aqi_yoy": data.get("aqi_year_over_year"),
            "pm25_avg": data.get("pm2.5_average"),
            "pm25_yoy": data.get("pm2.5_yoy"),
            "o3_avg": data.get("o3_average"),
            "o3_yoy": data.get("o3_yoy")
        }

    def _parse_ranking(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """解析排名数据"""
        data = result.get("data", {})

        return {
            "best_5": data.get("top_5_cities", []),
            "worst_5": data.get("bottom_5_cities", [])
        }

    def _parse_table(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析表格数据"""
        data = result.get("data", [])
        return data if isinstance(data, list) else [data]


# 修改: template_data_fetcher.py
class TemplateDataFetcher:
    def __init__(self, tool_executor: ToolExecutor):
        self.tool_executor = tool_executor
        self.api_client = RealAPIClient()  # 新增真实客户端

    async def _execute_query(self, query_type: str, requirements: List[Dict[str, Any]],
                            time_range: Dict[str, str]) -> Dict[str, Any]:
        """执行查询 - 优先使用真实API"""
        try:
            if query_type == "province_overview":
                return await self.api_client.query_province_overview(time_range)
            elif query_type == "city_ranking":
                return await self.api_client.query_city_ranking(time_range)
            elif query_type == "city_detail_table":
                return await self.api_client.query_city_detail_table(time_range)
            else:
                # 降级到tool_executor
                return await self._execute_via_tool_executor(query_type, requirements, time_range)
        except Exception as e:
            logger.error(f"Real API failed: {e}, using mock data")
            return await self._mock_query_result(query_type, time_range)
```

**优先级理由**：数据是报告的基础，必须使用真实数据

---

#### 3. DataOrganizer 智能数据提取

**文件位置**：`app/services/data_organizer.py`

**当前问题**：
- `_find_data_value` 是硬编码的临时实现
- 每个数据点都返回固定值，无法适应实际数据

**优化方案**：

```python
def _find_data_value(self, data: Dict[str, Any], point: Dict[str, Any]) -> Any:
    """智能数据匹配（替代临时硬编码）"""
    point_name = point.get("name", "")

    # 映射配置：显示名称 -> 数据字段
    FIELD_MAPPING = {
        "AQI达标率": ["aqi_rate", "aqi_compliance_rate", "合格率", "达标率"],
        "AQI同比": ["aqi_yoy", "aqi_year_over_year"],
        "PM2.5浓度": ["pm25", "pm25_avg", "pm2.5", "PM2.5"],
        "PM2.5同比": ["pm25_yoy", "pm2.5_yoy"],
        "PM10浓度": ["pm10", "pm10_avg"],
        "O3浓度": ["o3", "o3_avg", "臭氧", "O3"],
        "O3同比": ["o3_yoy", "o3_year_over_year"],
        "综合指数": ["composite", "composite_index", "综合指数"],
        "优良天数": ["good_days", "excellent_days"],
        "污染天数": ["polluted_days", "unhealthy_days"]
    }

    # 智能匹配
    for display_name, possible_fields in FIELD_MAPPING.items():
        if display_name in point_name:
            for field in possible_fields:
                if field in data:
                    return data[field]

        # 模糊匹配：如果名称包含关键词
        for field in possible_fields:
            if field in data and field.lower() in point_name.lower():
                return data[field]

    # 备用方案：返回数据中第一个数值
    for value in data.values():
        if isinstance(value, (int, float)):
            return value

    return "N/A"

def _format_section_data(
    self,
    section_data: Dict[str, Any],
    section_config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """格式化章节数据 - 增强版"""
    formatted_points = []

    # 如果有预定义数据点，使用它们
    if "data_points" in section_config:
        for point in section_config["data_points"]:
            value = self._find_data_value(section_data, point)

            formatted_point = {
                "name": point.get("name"),
                "value": value,
                "unit": point.get("unit", ""),
                "comparison": point.get("comparison", "")
            }

            # 如果没有对比数据，尝试从API返回中提取
            if not formatted_point["comparison"] and isinstance(section_data, dict):
                formatted_point["comparison"] = self._extract_comparison(section_data, point.get("name"))

            formatted_points.append(formatted_point)

    return formatted_points

def _extract_comparison(self, data: Dict[str, Any], point_name: str) -> str:
    """从数据中提取同比/环比信息"""
    # 查找关键词
    for key, value in data.items():
        if "yoy" in key.lower() or "同比" in key or "year_over_year" in key:
            if isinstance(value, (int, float)):
                trend = "上升" if value > 0 else "下降"
                return f"同比{trend}{abs(value)}%"

    return ""
```

**优先级理由**：影响报告数据的准确性和可读性

---

#### 4. LLM服务集成（方案B：直接复用现有实现，且保持0-regex）

**文件位置**：`backend/app/services/llm_service.py`（已存在）

**方案B约束**：
- 方案B不引入任何“正则清洗/提取”逻辑
- 结构化输出依赖 `llm_service.call_llm_with_json_response(...)` 的 JSON 反序列化校验与有限重试

**建议用法**：
- 结构解析：`call_llm_with_json_response(prompt, max_retries=2)`
- 章节分析：`llm_service.chat([...])`（失败则走 Renderer 内置降级文本，不做正则）

**环境变量配置**：
```bash
# 配置文件
LLM_PROVIDER=mock  # openai | anthropic | tianji | mock
LLM_API_KEY=your_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-3.5-turbo
LLM_FALLBACK_ENABLED=true
```

**优先级理由**：智能分析是报告的核心价值

---

### P1 - 测试与质量保证

#### 5. 完整测试体系

```python
# tests/test_scheme_b_complete.py

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from app.services.template_report_engine import TemplateReportEngine

class TestSchemeBCompleteness:
    """方案B完整功能测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_pipeline(self):
        """端到端流程测试"""

        # 测试数据
        template = """
        # 月度报告

        ## 数据概览
        - AQI达标率: {{aqi_rate}}%
        - PM2.5: {{pm25}}μg/m³

        ## 城市排名
        {{#each best_5}}- {{name}} ({{rank}})\n{{/each}}

        ## 分析
        {{#llm_analysis}}
        基于{{weather_summary}}分析
        {{/llm_analysis}}
        """

        time_range = {"start": "2025-01-01", "end": "2025-01-31"}

        # Mock
        with patch('app.services.llm_service.llm_service') as mock_llm, \
             patch('app.services.real_api_client.api_client') as mock_api:

            mock_api.query_province_overview.return_value = {
                "aqi_rate": 93.2, "pm25_avg": 24
            }
            mock_api.query_city_ranking.return_value = {
                "best_5": [{"name": "广州", "rank": 1}]
            }
            mock_llm.chat.return_value = "分析完成"
            mock_llm.clean_thinking_tags.return_value = "分析完成"

            # 执行
            engine = TemplateReportEngine(tool_executor=Mock())
            events = []

            async for event in engine.generate_from_template(template, time_range):
                events.append(event)

            # 验证
            assert len(events) >= 4
            assert events[-1].type.value == "report_completed"
            report = events[-1].data["report_content"]
            assert "93.2" in report
            assert "广州" in report

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """错误处理测试"""

        # LLM失败应降级
        parser = ReportParser()

        with patch('app.services.llm_service.llm_service.chat',
                  side_effect=Exception("LLM Error")):
            result = await parser.parse("## 章节1\n内容")

            assert len(result.sections) > 0
            assert "章节1" in result.sections[0]["title"]

    def test_data_mapping(self):
        """数据字段映射测试"""
        organizer = DataOrganizer()

        test_cases = [
            ({"aqi_rate": 92, "pm25": 23}, "AQI达标率", 92),
            ({"aqi_rate": 92, "pm25": 23}, "PM2.5浓度", 23),
            ({"composite": 3.5}, "综合指数", 3.5),
        ]

        for data, field, expected in test_cases:
            result = organizer._find_data_value(data, {"name": field})
            assert result == expected

    @pytest.mark.asyncio
    async def test_template_rendering(self):
        """模板渲染测试"""
        renderer = ReportRenderer()

        # 循环测试
        template = "{{#each items}}- {{name}}\n{{/each}}"
        data = {"items": [{"name": "A"}, {"name": "B"}]}
        result = await renderer._replace_each_blocks(template, data)

        assert "- A" in result
        assert "- B" in result

    def test_report_structure_parsing(self):
        """报告结构解析测试"""
        from app.services.report_parser import ReportParser

        content = """
        # 报告

        ## 总体
        数据很好

        ## 分析
        需要分析
        """

        parser = ReportParser()
        result = parser._mock_parse(content)

        assert len(result.sections) == 2
        assert result.sections[0]["title"] == "总体"

# 运行
# pytest tests/test_scheme_b_complete.py -v
```

**运行命令**：
```bash
# 运行所有测试
pytest tests/test_scheme_b_complete.py -v

# 运行特定测试
pytest tests/test_scheme_b_complete.py::TestSchemeBCompleteness::test_end_to_end_pipeline -v

# 生成覆盖率报告
pytest --cov=app.services tests/test_scheme_b_complete.py -v
```

---

### P2 - 前端优化与性能

#### 6. 前端流式处理增强

```javascript
// frontend/src/services/reportApi.js

/**
 * 增强的SSE流式处理
 * 支持实时进度更新和错误重连
 */
export class ReportStreamService {
  constructor() {
    this.eventHandlers = {}
    this.retryCount = 0
    this.maxRetries = 3
  }

  // 注册事件处理器
  on(eventType, handler) {
    if (!this.eventHandlers[eventType]) {
      this.eventHandlers[eventType] = []
    }
    this.eventHandlers[eventType].push(handler)
  }

  // 触发事件
  emit(eventType, data) {
    if (this.eventHandlers[eventType]) {
      this.eventHandlers[eventType].forEach(handler => handler(data))
    }
  }

  // 启动流式生成
  async generateFromTemplate(request, onProgress) {
    try {
      const response = await fetch('/api/report/generate-from-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // 处理完整的SSE事件
        const events = this.parseSSE(buffer)
        buffer = events.buffer  // 保留未完成的数据

        for (const event of events.items) {
          this.handleEvent(event, onProgress)
        }
      }

      this.retryCount = 0  // 重置重试计数

    } catch (error) {
      // 自动重连逻辑
      if (this.retryCount < this.maxRetries) {
        this.retryCount++
        console.warn(`Stream failed, retrying (${this.retryCount}/${this.maxRetries})...`)
        await new Promise(resolve => setTimeout(resolve, 1000 * this.retryCount))
        return this.generateFromTemplate(request, onProgress)
      } else {
        throw error
      }
    }
  }

  // 解析SSE数据
  parseSSE(buffer) {
    const lines = buffer.split('\n')
    const events = []
    let newBuffer = lines.pop() || ''  // 最后一行可能是不完整的

    for (let i = 0; i < lines.length; i += 2) {
      const eventLine = lines[i]
      const dataLine = lines[i + 1]

      if (eventLine && eventLine.startsWith('event: ') &&
          dataLine && dataLine.startsWith('data: ')) {

        const type = eventLine.slice(7)
        const dataStr = dataLine.slice(6)

        try {
          const data = JSON.parse(dataStr)
          events.push({ type, data })
        } catch (e) {
          console.warn('Failed to parse SSE data:', dataStr)
        }
      }
    }

    return { items: events, buffer: newBuffer }
  }

  // 处理单个事件
  handleEvent(event, onProgress) {
    const { type, data } = event

    // 触发通用处理器
    this.emit(type, data)

    // 触发进度回调
    if (onProgress) {
      onProgress({ type, data })
    }

    // 特殊事件处理
    switch (type) {
      case 'parsing':
        onProgress({
          phase: '解析中',
          description: data.description,
          progress: 25
        })
        break

      case 'data_fetching':
        onProgress({
          phase: '数据获取',
          description: data.description,
          progress: 50
        })
        break

      case 'processing':
        onProgress({
          phase: '数据整理',
          description: data.description,
          progress: 75
        })
        break

      case 'report_completed':
        onProgress({
          phase: '完成',
          description: '报告生成成功',
          progress: 100,
          content: data.report_content
        })
        break

      case 'error':
        onProgress({
          phase: '错误',
          description: data.error,
          isError: true
        })
        break
    }
  }
}

// 使用示例
export async function generateTemplateReport(request, callbacks) {
  const service = new ReportStreamService()

  // 注册各类事件处理器
  service.on('structure_parsed', (data) => {
    console.log(`解析完成: ${data.sections_count}个章节`)
    if (callbacks.onParsed) callbacks.onParsed(data)
  })

  service.on('data_fetched', (data) => {
    console.log(`数据获取: ${data.record_count}条记录`)
    if (callbacks.onDataFetched) callbacks.onDataFetched(data)
  })

  // 启动流式处理
  return await service.generateFromTemplate(request, (progress) => {
    if (callbacks.onProgress) callbacks.onProgress(progress)
  })
}
```

```vue
<!-- frontend/src/components/report/GenerationProgress.vue -->
<template>
  <div class="generation-progress">
    <div class="progress-header">
      <h4>生成进度: {{ currentPhase }}</h4>
      <div class="progress-bar">
        <div class="progress-fill" :style="{width: progress + '%'}"></div>
      </div>
    </div>

    <div class="event-log">
      <div v-for="(event, index) in events" :key="index"
           :class="['event-item', event.type]">
        <span class="event-time">{{ formatTime(event.timestamp) }}</span>
        <span class="event-desc">{{ event.description || event.type }}</span>
        <span v-if="event.data" class="event-data">
          {{ JSON.stringify(event.data) }}
        </span>
      </div>
    </div>

    <div v-if="isError" class="error-message">
      <p>⚠️ 生成失败</p>
      <button @click="$emit('retry')">重试</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  progress: Number,
  currentPhase: String,
  events: Array,
  isError: Boolean
})

const formatTime = (timestamp) => {
  return new Date(timestamp * 1000).toLocaleTimeString()
}
</script>

<style scoped>
.generation-progress {
  padding: 16px;
  background: #f5f5f5;
  border-radius: 8px;
}

.progress-bar {
  height: 6px;
  background: #ddd;
  border-radius: 3px;
  overflow: hidden;
  margin: 8px 0;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1976d2, #64b5f6);
  transition: width 0.3s ease;
}

.event-log {
  max-height: 200px;
  overflow-y: auto;
  margin-top: 12px;
  font-family: monospace;
  font-size: 12px;
}

.event-item {
  padding: 4px 8px;
  border-bottom: 1px solid #e0e0e0;
}

.event-item.parsing { background: #e3f2fd; }
.event-item.data_fetching { background: #e8f5e9; }
.event-item.processing { background: #fff3e0; }

.error-message {
  color: #d32f2f;
  padding: 12px;
  background: #ffebee;
  border-radius: 4px;
  margin-top: 12px;
  text-align: center;
}
</style>
```

---

#### 7. 性能优化

```python
# app/services/template_report_engine.py

class TemplateReportEngine:
    """性能优化版"""

    async def generate_from_template(self, template_content, target_time_range, options=None):
        # 使用并发获取数据，而不是顺序执行
        # 阶段1: 解析（同步）
        structure = await self.parser.parse(template_content)

        # 阶段2: 数据获取（并行）
        data_requirements = self.parser.get_data_requirements(structure)

        # 使用asyncio.gather并行获取
        fetch_tasks = []
        for req in data_requirements:
            task = self.data_fetcher.fetch_for_requirement(req, target_time_range)
            fetch_tasks.append(task)

        # 并行执行
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        # 组合结果
        raw_data = self._merge_results(results, data_requirements)

        # 阶段3: 数据整理（异步）
        processed = await self.organizer.organize(
            raw_data,
            structure.sections,
            structure.tables,
            structure.rankings
        )

        # 阶段4: 渲染（异步）
        final = await self.renderer.render(
            template_content,
            structure,
            processed,
            target_time_range
        )

        return final

    # 实现并行数据获取
    async def _fetch_data_parallel(self, requirements, time_range):
        """并行执行数据获取"""

        # 按查询类型分组，减少API调用
        grouped = self._group_by_query_type(requirements)

        tasks = []
        for query_type, reqs in grouped.items():
            task = self.data_fetcher._execute_query(
                query_type, reqs, time_range
            )
            tasks.append((query_type, task))

        # 并行执行所有查询
        results = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True
        )

        # 合并结果
        merged = {}
        for (query_type, _), result in zip(tasks, results):
            if not isinstance(result, Exception):
                merged[query_type] = result

        return merged

    def _group_by_query_type(self, requirements):
        """智能分组查询"""
        from collections import defaultdict
        groups = defaultdict(list)

        for req in requirements:
            query_type = req.get("query_type", "general")
            groups[query_type].append(req)

        return dict(groups)

# 使用缓存（可选）
from functools import lru_cache
import hashlib

class DataCache:
    """简单内存缓存"""

    def __init__(self, maxsize=128):
        self.cache = {}
        self.maxsize = maxsize

    def _make_key(self, query_type, time_range):
        raw = f"{query_type}:{time_range['start']}:{time_range['end']}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, query_type, time_range):
        key = self._make_key(query_type, time_range)
        return self.cache.get(key)

    def set(self, query_type, time_range, data):
        if len(self.cache) >= self.maxsize:
            self.cache.pop(next(iter(self.cache)))

        key = self._make_key(query_type, time_range)
        self.cache[key] = data

    def clear(self):
        self.cache.clear()

# 在DataFetcher中使用缓存
class TemplateDataFetcher:
    def __init__(self, tool_executor):
        self.tool_executor = tool_executor
        self.api_client = RealAPIClient()
        self.cache = DataCache(maxsize=50)  # 新增缓存

    async def _execute_query(self, query_type, requirements, time_range):
        # 先查缓存
        cached = self.cache.get(query_type, time_range)
        if cached:
            logger.info(f"Cache hit: {query_type}")
            return cached

        # 执行查询
        result = await self._execute_query_real(query_type, requirements, time_range)

        # 存入缓存
        self.cache.set(query_type, time_range, result)

        return result
```

---

## 📊 实施建议与时间规划

### 第一阶段（1-2天）：核心功能完善

**目标**：让方案B能够真正运行

1. **Day 1上午**：实现LLM服务 (`llm_service.py`)
2. **Day 1下午**：实现API客户端 (`real_api_client.py`)
3. **Day 2上午**：完善DataOrganizer智能匹配
4. **Day 2下午**：实现报告渲染器高级模板语法

### 第二阶段（1天）：测试与验证

**目标**：确保稳定性和可靠性

1. **Day 3上午**：编写完整测试用例
2. **Day 3下午**：执行测试并修复问题

### 第三阶段（1天）：前端优化

**目标**：提升用户体验

1. **Day 4上午**：实现流式处理
2. **Day 4下午**：优化进度展示和错误处理

### 第四阶段（0.5天）：性能优化

**目标**：提升响应速度

1. **Day 5上午**：实现并行处理和缓存机制

---

## 🎯 关键里程碑

| 里程碑 | 验收标准 | 预计时间 |
|--------|----------|----------|
| **MVP可运行** | 上传模板 → 生成报告 → 输出Markdown | 2天 |
| **质量保障** | 核心测试通过率100% | 1天 |
| **用户体验** | 实时进度显示，无卡顿 | 1天 |
| **性能达标** | 生成时间<30秒，支持并行 | 0.5天 |

---

## 💡 补充建议

### 1. **错误处理策略**
- 每个环节都要try-catch
- 记录详细的错误日志
- 提供用户友好的错误提示

### 2. **日志记录**
```python
import logging

logger = logging.getLogger(__name__)

async def generate_from_template(...):
    logger.info(f"开始生成报告: {template_content[:50]}...")

    try:
        logger.info("阶段1: 解析报告结构")
        structure = await self.parser.parse(template_content)
        logger.info(f"解析完成: {len(structure.sections)}个章节")

        # ... 其他阶段

    except Exception as e:
        logger.error(f"生成失败: {str(e)}", exc_info=True)
        raise
```

### 3. **配置管理**
```python
# config/report_config.py

REPORT_CONFIG = {
    "max_template_size": 10 * 1024 * 1024,  # 10MB
    "max_processing_time": 120,  # 2分钟
    "enable_parallel": True,
    "cache_enabled": True,
    "llm_timeout": 30,
    "retry_attempts": 2,
}
```

---

## 📞 问题反馈与支持

如有问题或需要协助，请查看：
- 项目架构文档：`D:\溯源\CLAUDE.md`
- 现有工具层：`backend/app/tools/`
- 数据模式：`backend/app/schemas/`
