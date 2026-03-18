"""
查询济宁市常规站点区域对比数据工具

支持两种模式：
1. 城市级区域对比：获取济宁市及各区县的污染物时序数据
2. 站点级区域对比：获取济宁市所有国控站点的污染物时序数据

主要用于济宁市空气质量溯源分析
"""
from typing import Dict, Any, List, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.http_client import http_client
from app.utils.data_standardizer import get_data_standardizer
from app.utils.data_features_extractor import DataFeaturesExtractor

logger = structlog.get_logger()


class GetJiningRegularStationsTool(LLMTool):
    """
    查询济宁市区域对比数据工具

    支持两种查询模式：
    1. 城市级对比：查询济宁市及各区县的污染物时序数据
    2. 站点级对比：查询济宁市所有国控站点的污染物时序数据

    使用 LLM-first 模式：完全由LLM决策查询内容，代码不做任何自动追加
    """

    def __init__(self):
        function_schema = {
            "name": "get_jining_regular_stations",
            "description": """
查询济宁市区域对比污染物时序数据。

【核心功能】
- 查询济宁市及各区县的污染物时序数据
- 查询济宁市所有国控站点的污染物时序数据
- 返回统一格式数据（UDF v2.0），供下游分析和可视化使用

【使用场景】
- 济宁市空气质量概况和区县排名
- 区域污染物浓度时序对比分析
- 城市内部空间分布分析

【输入参数】
- question: 完整的自然语言查询问题，需包含：
  * 区域范围（如"济宁市"、"济宁市任城区"、"邹城市"等）
  * 时间范围（如"2025-01-01至2025-12-31"）
  * 污染物类型（如"PM2.5"、"O3"、"AQI"）
  * 时间粒度（如"小时数据"、"日数据"、"月数据"）

【重要】
- 完全由LLM决定查询的时间粒度、数据类型等
- 代码不自动追加任何内容
- 工具直接转发LLM生成的问题给UQP接口

示例："查询济宁市各区县空气质量综合排名，TimePoint=2025-01-01至2025-12-31，时间粒度为月度，返回各区县的AQI达标率、PM2.5浓度、PM10浓度、O3浓度、综合指数等指标，按综合指数排序"

【返回数据】
- data_id: 数据引用ID（UDF v2.0格式）
- 包含济宁市各区县/站点的污染物时序数据
- 可直接传递给可视化工具生成多系列时序图
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "自然语言查询问题，描述要查询的区域对比数据"
                    }
                },
                "required": ["question"]
            }
        }

        super().__init__(
            name="get_jining_regular_stations",
            description="Query Jining regional comparison data for air quality analysis - Context-Aware V2",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: Any,
        question: str,
        comparison_type: str = "city",
        chart_title: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行区域对比数据查询

        完全依赖LLM生成的自然语言question和UQP接口的自然语言理解能力。

        Args:
            context: 执行上下文
            question: 完整的自然语言查询问题（由 LLM 生成，直接发送给UQP接口）
            comparison_type: 对比类型 ("city" 城市级 | "station" 站点级)
            chart_title: 图表标题

        Returns:
            UDF v2.0格式的查询结果
        """
        logger.info(
            "jining_regional_query_start",
            question=question,
            comparison_type=comparison_type,
            chart_title=chart_title,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        try:
            # 直接使用question发送给UQP接口
            all_records = await self._query_pollutant_data_direct(
                question=question,
                comparison_type=comparison_type
            )

            if not all_records:
                return self._create_error_response("未查询到符合条件的监测数据", question)

            # 调试日志
            for i, rec in enumerate(all_records[:3]):
                logger.info(
                    f"jining_raw_record_{i}_debug",
                    district=rec.get("district"),
                    name=rec.get("name"),
                    o3=rec.get("o3"),
                    code=rec.get("code")
                )

            # 数据标准化
            data_standardizer = get_data_standardizer()
            standardized_records = data_standardizer.standardize(all_records)

            logger.info(
                "jining_regional_data_standardized",
                raw_count=len(all_records),
                standardized_count=len(standardized_records)
            )

            # 保存到上下文
            data_features = DataFeaturesExtractor.extract_features(
                standardized_records,
                schema_type="guangdong_stations"
            )

            # 推断污染物类型和区域信息
            pollutant = self._infer_pollutant_from_data(standardized_records)
            districts_from_data = self._extract_districts_from_data(standardized_records)

            # 根据对比类型生成schema名称
            schema_name = f"jining_{comparison_type}_comparison"

            data_id = context.data_manager.save_data(
                data=standardized_records,
                schema=schema_name,
                metadata={
                    "question": question,
                    "source": "jining_regional_comparison",
                    "data_type": f"jining_{comparison_type}_comparison",
                    "schema_version": "v2.0",
                    "schema_type": schema_name,
                    "generator": "get_jining_regular_stations",
                    "scenario": f"jining_{comparison_type}_comparison",
                    "comparison_type": comparison_type,
                    "chart_title": chart_title,
                    "districts": districts_from_data,
                    "pollutant": pollutant,
                    "field_mapping_applied": True,
                    "field_mapping_info": data_standardizer.get_field_mapping_info(),
                    "data_features": data_features
                }
            )

            handle = context.data_manager.get_handle(data_id)

            logger.info(
                "jining_regional_data_saved",
                data_id=data_id,
                record_count=handle.record_count,
                comparison_type=comparison_type
            )

            # 生成摘要信息
            districts_summary = "、".join(districts_from_data[:5])
            if len(districts_from_data) > 5:
                districts_summary += f"等{len(districts_from_data)}个区域"
            summary = f"[OK] 成功获取{districts_summary}的{pollutant}数据共{handle.record_count}条"

            return {
                "status": "success",
                "success": True,
                "data": standardized_records[:50],
                "metadata": {
                    "tool_name": "get_jining_regular_stations",
                    "data_id": data_id,
                    "registry_schema": schema_name,
                    "record_count": handle.record_count,
                    "question": question,
                    "districts": districts_from_data,
                    "pollutant": pollutant,
                    "comparison_type": comparison_type,
                    "chart_title": chart_title,
                    "analysis_type": f"jining_{comparison_type}_comparison"
                },
                "summary": f"{summary}，已保存为 {data_id}。"
            }

        except Exception as e:
            logger.error(
                "jining_regional_query_failed",
                question=question,
                error=str(e),
                exc_info=True
            )
            return self._create_error_response(str(e), question)

    async def _query_pollutant_data_direct(
        self,
        question: str,
        comparison_type: str = "city"
    ) -> List[Dict[str, Any]]:
        """
        直接使用question查询数据，完全依赖UQP接口的自然语言理解

        Args:
            question: LLM生成的自然语言查询问题
            comparison_type: 对比类型

        Returns:
            查询结果记录列表
        """
        url = "http://180.184.91.74:9096/api/uqp/query"

        logger.info(
            "jining_direct_query_to_uqp",
            question=question,
            comparison_type=comparison_type
        )

        all_records = []

        try:
            response = await http_client.post(
                url,
                json_data={"question": question},
                timeout=120
            )
            records = self._seek_records(response)
            if records:
                # 调试：打印原始数据结构
                logger.info(
                    "jining_raw_response_structure",
                    first_record_keys=list(records[0].keys()) if records else [],
                    has_pollutants=any(k in records[0] for k in ['pM2_5', 'o3', 'AQI']) if records else False
                )

                # 统计有多少条记录包含完整数据
                complete_count = sum(1 for r in records if any(k in r for k in ['pM2_5', 'o3', 'AQI']))
                logger.info("jining_complete_records_count", complete_count=complete_count, total=len(records))

                for record in records:
                    filtered_record = {
                        k: v for k, v in record.items()
                        if not k.endswith('_IAQI') and not k.endswith('_iaqi')
                    }
                    if "code" in filtered_record and "city_code" not in filtered_record:
                        filtered_record["city_code"] = filtered_record["code"]
                    all_records.append(filtered_record)

                logger.info(
                    "jining_uqp_query_success",
                    question=question,
                    records_count=len(records)
                )

        except Exception as e:
            logger.warning(
                "jining_uqp_query_failed",
                question=question,
                error=str(e)
            )

        if all_records:
            logger.info(
                "jining_uqp_query_complete",
                question=question,
                total_records=len(all_records)
            )
            return all_records
        else:
            logger.warning(
                "jining_uqp_query_no_records",
                question=question
            )
            return []

    def _infer_pollutant_from_data(self, records: List[Dict[str, Any]]) -> str:
        """从数据中推断污染物类型"""
        if not records:
            return "O3"

        first_record = records[0]

        # 检查O3_8h字段
        o3_8h_fields = ["O3_8h", "O3_8H", "O38H", "O38h", "臭氧8小时", "臭氧8小时平均", "O3-8h"]
        for field in o3_8h_fields:
            if field in first_record or any(field.lower() == k.lower() for k in first_record.keys()):
                return "O3_8h"

        # 扩展的污染物字段列表
        pollutant_fields = [
            "PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "AQI",
            "PM25", "臭氧", "二氧化氮", "二氧化硫", "一氧化碳",
            "臭氧(O3)", "PM2.5(细颗粒物)", "PM10(颗粒物)"
        ]

        for field in pollutant_fields:
            if field in first_record or any(field.lower() in k.lower() for k in first_record.keys()):
                normalized = field.replace("(", " (").replace(")", ")").split("(")[0].strip()
                return normalized

        return "O3"

    def _extract_districts_from_data(self, records: List[Dict[str, Any]]) -> List[str]:
        """从数据中提取区县列表"""
        districts = set()

        if not records:
            return []

        first_record = records[0]
        logger.info(
            "jining_extract_districts_debug",
            first_record_keys=list(first_record.keys())[:15],
            district_value=first_record.get("district"),
            district_name_value=first_record.get("districtName"),
            name_value=first_record.get("name")
        )

        # 济宁市各区县
        jining_districts = [
            "任城区", "兖州区", "曲阜市", "泗水县", "邹城市",
            "微山县", "鱼台县", "金乡县", "嘉祥县", "汶上县",
            "梁山县", "济宁高新区", "太白湖区"
        ]

        for record in records:
            district = None

            # 1. 检查标准化后的 district 字段
            district = record.get("district")
            if district and district not in ["济宁市", None]:
                districts.add(str(district).replace("市", "").replace("县", "").strip())
                continue

            # 2. 检查 districtName
            district_name = record.get("districtName")
            if district_name:
                for jd in jining_districts:
                    if jd in district_name or district_name in jd:
                        districts.add(jd.replace("市", "").replace("县", "").strip())
                        break
                if districts:
                    continue

            # 3. 从站点名称推断区县
            station_name = record.get("station_name") or record.get("name", "")
            for jd in jining_districts:
                if jd in station_name:
                    districts.add(jd.replace("市", "").replace("县", "").strip())
                    break

        logger.info(
            "jining_extract_districts_result",
            districts_count=len(districts),
            districts=list(districts)
        )

        return sorted(list(districts))

    def _seek_records(self, payload: Any) -> Optional[List[Dict[str, Any]]]:
        """
        从UQP响应中提取记录列表

        支持多种响应结构
        """
        if isinstance(payload, dict):
            logger.info(
                "jining_seek_records_debug",
                response_keys=list(payload.keys())[:15],
                has_result="result" in payload,
                has_data="data" in payload
            )
        elif isinstance(payload, list):
            logger.info("jining_seek_records_debug", response_type="list", length=len(payload))

        if isinstance(payload, list):
            for item in payload:
                nested = self._seek_records(item)
                if nested:
                    return nested
            return self._ensure_dict_list(payload)

        if isinstance(payload, dict):
            if "result" in payload:
                result = payload["result"]
                if isinstance(result, list):
                    return result
                elif isinstance(result, dict):
                    if "list" in result:
                        return result["list"]
                    elif "data" in result:
                        nested = result["data"]
                        if isinstance(nested, list):
                            return nested
                        elif isinstance(nested, dict) and "list" in nested:
                            return nested["list"]

            if "data" in payload:
                inner = payload["data"]
                if isinstance(inner, list):
                    return inner
                elif isinstance(inner, dict):
                    if "result" in inner:
                        result = inner["result"]
                        if isinstance(result, list):
                            return result
                    if "list" in inner:
                        return inner["list"]

            # 查找其他可能的记录字段
            for key in ("data", "result", "results", "stations", "value", "payload"):
                value = payload.get(key)
                if isinstance(value, list):
                    normalised = self._ensure_dict_list(value)
                    if normalised:
                        return normalised

            # 递归查找嵌套结构
            for value in payload.values():
                nested = self._seek_records(value)
                if nested:
                    return nested

        return None

    def _ensure_dict_list(self, payload: List[Any]) -> List[Dict[str, Any]]:
        """确保返回的是字典列表"""
        normalised: List[Dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                nested = self._seek_records(item)
                if nested:
                    return nested
                normalised.append(item)
        return normalised

    def _create_error_response(self, error_msg: str, question: str) -> Dict[str, Any]:
        """创建错误响应"""
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "metadata": {
                "tool_name": "get_jining_regular_stations",
                "error_type": "execution_failed",
                "question": question
            },
            "summary": f"[FAIL] 济宁区域对比数据查询失败: {error_msg[:100]}"
        }
