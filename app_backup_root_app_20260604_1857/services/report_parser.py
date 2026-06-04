"""
报告结构解析器 - 方案B：0-regex LLM驱动
场景2-B：临时报告（结构化拆解）
"""
from typing import Dict, Any, List
import structlog

from app.schemas.report_generation import ReportStructure
from app.services.llm_service import llm_service

logger = structlog.get_logger()


class ReportParser:
    """报告结构解析器 - LLM驱动（严格0-regex）"""

    async def parse(self, content: str) -> ReportStructure:
        """
        方案B：严格LLM解析（0-regex）

        策略：
        - Prompt 强约束：只能输出一个JSON对象（无解释文本/无Markdown围栏）
        - 失败处理：有限重试（2次），仍失败则抛错（不做正则兜底）

        Args:
            content: 报告内容（Markdown格式）

        Returns:
            ReportStructure: 包含章节、数据点、表格、排名规则的结构
        """
        logger.info("Parsing report structure using LLM (scheme B: no-regex)")

        prompt = self._build_parse_prompt(content)

        # ✅ 方案B核心：不做任何正则清洗/兜底解析；完全信任LLM输出结构化JSON
        try:
            result_data = await llm_service.call_llm_with_json_response(
                prompt=prompt,
                max_retries=2
            )
            return ReportStructure(**result_data)
        except Exception as e:
            logger.error("llm_parsing_failed_no_regex_fallback", error=str(e), exc_info=True)
            raise

    def _build_parse_prompt(self, content: str) -> str:
        """
        构建严格约束的解析prompt

        Args:
            content: 报告内容

        Returns:
            str: 解析prompt
        """
        prompt = f"""你是报告结构解析器。请把输入的Markdown报告解析为结构化JSON对象。

【硬性要求】
1. 只能输出一个JSON对象（以{{开头、以}}结尾），不要输出任何解释文字，不要输出Markdown代码块标记。
2. 必须包含以下顶层字段：time_range、sections、tables、rankings、analysis_sections（缺失时用空数组/空对象，不能省略）。
3. sections 每项必须包含：id、title、type、data_points（允许为空数组）。

报告内容：
{content}

请返回以下JSON格式：
{{
    "time_range": {{
        "original": "原始时间描述，如'1-6月'",
        "start_month": 1,
        "end_month": 6,
        "year": 2025,
        "display": "2025年1-6月"
    }},
    "sections": [
        {{
            "id": "section_id",
            "title": "章节标题",
            "type": "text_with_data|llm_generated",
            "data_points": [
                {{
                    "name": "数据名称",
                    "value": "数值",
                    "unit": "单位",
                    "comparison": "同比/环比描述"
                }}
            ]
        }}
    ],
    "tables": [
        {{
            "id": "table_id",
            "title": "表格标题",
            "columns": ["列1", "列2", "列3"],
            "row_type": "city|district|month"
        }}
    ],
    "rankings": [
        {{
            "id": "ranking_id",
            "description": "排名描述",
            "metric": "排名指标",
            "order": "asc|desc",
            "top_n": 5
        }}
    ],
    "analysis_sections": [
        {{
            "id": "analysis_id",
            "title": "分析章节标题",
            "type": "llm_generated",
            "input_data": ["weather", "emissions", "control_measures"]
        }}
    ]
}}

"""
        return prompt

    def _mock_parse(self, content: str) -> ReportStructure:
        """
        模拟解析实现 - 0-regex兜底（最简方案）

        仅识别"## "标题，不提取内容，不提取数据点

        Args:
            content: 报告内容

        Returns:
            ReportStructure: 模拟的结构（data_points为空）
        """
        sections = []
        tables = []
        rankings = []
        analysis_sections = []

        # 仅做行扫描识别标题（无正则）
        for line in content.splitlines():
            if line.startswith("## "):
                title = line[3:].strip()
                if title:
                    sections.append({
                        "id": f"section_{len(sections)}",
                        "title": title,
                        "type": "text_with_data",
                        "data_points": []  # 必须为空，因为没有LLM推断
                    })

        # 构建时间范围（模拟）
        time_range = {
            "original": "unknown",
            "start_month": 1,
            "end_month": 12,
            "year": 2025,
            "display": "unknown"
        }

        return ReportStructure(
            time_range=time_range,
            sections=sections,
            tables=tables,
            rankings=rankings,
            analysis_sections=analysis_sections
    )

    def get_data_requirements(self, structure: ReportStructure) -> List[Dict[str, Any]]:
        """
        从报告结构中提取数据需求 - 0-regex原则

        关键：不做任何文本提取，仅消费LLM解析结果

        Args:
            structure: 报告结构

        Returns:
            List[Dict[str, Any]]: 数据需求列表
        """
        requirements: List[Dict[str, Any]] = []

        # 章节：以LLM解析的section为准（必须包含 data_points）
        for section in structure.sections:
            if not isinstance(section, dict):
                logger.warning(f"section_not_dict: {section}")
                continue

            section_id = section.get("id")
            data_points = section.get("data_points") or []

            # 方案B要求：必须有明确的data_points，否则视为无效章节
            if not section_id:
                logger.warning(f"section_missing_id: {section}")
                continue

            # 关键：不推断，只消费
            if data_points:
                requirements.append({
                    "section_id": section_id,
                    "data_points": data_points,
                    "query_type": self._infer_query_type(data_points)
                })
            else:
                logger.info(f"section_has_no_data_points: {section_id}")

        # 表格需求
        for table in structure.tables:
            if isinstance(table, dict) and table.get("id"):
                requirements.append({
                    "section_id": table["id"],
                    "table": table,
                    "query_type": "city_detail_table"
                })

        # 排名需求
        for ranking in structure.rankings:
            if isinstance(ranking, dict) and ranking.get("id"):
                requirements.append({
                    "section_id": ranking["id"],
                    "ranking": ranking,
                    "query_type": "city_ranking"
                })

        return requirements

    def _infer_query_type(self, data_points: List[Dict]) -> str:
        """
        根据LLM提供的数据点推断查询类型

        注意：这是基于LLM解析结果的推断，不是从文本中“提取”
        """
        if not data_points:
            return "province_overview"

        names = [p.get("name", "") for p in data_points if isinstance(p, dict)]

        if any("排名" in n for n in names):
            return "city_ranking"
        elif any("综合指数" in n for n in names):
            return "city_detail_table"
        elif any("同比" in n for n in names):
            return "province_overview"
        else:
            return "province_overview"

# 测试辅助函数
async def _test_parser():
    """测试parser基本功能"""
    from app.services.tool_executor import ToolExecutor

    # 构建一个mock tool executor（不需要真实的）
    parser = ReportParser()

    # 测试内容
    content = """
# 2025年1-6月空气质量简报

## 总体状况
AQI达标率：92.3%，PM2.5浓度：23 μg/m³，同比改善5.2%

## 城市排名
空气质量较好的城市是广州、深圳、珠海。

## 数据表格
| 城市 | AQI达标率 | PM2.5浓度 |
|------|-----------|-----------|
| 广州 | 95.2%     | 20        |
| 深圳 | 96.8%     | 18        |

## 原因分析
主要受气象条件和排放强度共同影响。建议加强夏季臭氧污染防治。
"""

    try:
        structure = await parser.parse(content)
        print(f"✗ LLM服务异常，当前为开发环境")
    except Exception as e:
        print(f"✅ 期望异常: {e}")

    # 测试mock方案
    mock_struct = parser._mock_parse(content)
    print(f"\nMock解析结果:")
    print(f"  章节数: {len(mock_struct.sections)}")
    for s in mock_struct.sections:
        print(f"    - {s['title']}: {len(s['data_points'])}个数据点")

    # 测试get_data_requirements
    reqs = parser.get_data_requirements(mock_struct)
    print(f"  数据需求数: {len(reqs)}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(_test_parser())