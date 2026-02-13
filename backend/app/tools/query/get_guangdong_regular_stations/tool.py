"""
查询广东省常规站点区域对比数据工具

支持两种模式：
1. 城市级区域对比：获取目标城市及周边城市的污染物时序数据
2. 站点级区域对比：获取目标城市所有国控站点的污染物时序数据

主要用于快速溯源分析中的成因诊断（本地生成 vs 区域传输）
"""
from typing import Dict, Any, List, Optional
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.http_client import http_client
from app.utils.data_standardizer import get_data_standardizer
from app.utils.data_features_extractor import DataFeaturesExtractor
from app.services.external_apis import station_api

logger = structlog.get_logger()


class GetGuangdongRegularStationsTool(LLMTool):
    """
    查询广东省区域对比数据工具

    支持两种查询模式：
    1. 城市级对比：查询多个城市的污染物时序数据
    2. 站点级对比：查询目标城市所有国控站点的污染物时序数据

    使用 LLM-first 模式：完全由LLM决策查询内容，代码不做任何自动追加
    """

    def __init__(self):
        function_schema = {
            "name": "get_guangdong_regular_stations",
            "description": """
查询广东省区域对比污染物时序数据。

【核心功能】
- 查询多个城市的污染物时序数据
- 查询目标城市所有国控站点的污染物时序数据
- 自动调用站点API获取城市/站点列表
- 返回统一格式数据（UDF v2.0），供下游分析和可视化使用

【使用场景】
- 省级空气质量概况和城市排名
- 区域污染物浓度时序对比分析
- 城市内部空间分布分析

【输入参数】
- question: 完整的自然语言查询问题，需包含：
  * 城市名称（如"广州市、深圳市"或"广东省21个地市"）
  * 时间范围（如"2025-01-01至2025-12-31"）
  * 污染物类型（如"PM2.5"、"O3"、"AQI"）
  * 时间粒度（如"日数据"、"月数据"）

【重要】
- 完全由LLM决定查询的时间粒度、数据类型等
- 代码不自动追加任何内容（如"小时浓度数据"、"O3_8h"等）
- 工具直接转发LLM生成的问题给UQP接口

示例："查询广东省各城市空气质量综合排名，TimePoint=2025-01-01至2025-12-31，时间粒度为月度，返回所有城市的AQI达标率、PM2.5浓度、PM10浓度、O3浓度、综合指数等指标，按综合指数排序"

【返回数据】
- data_id: 数据引用ID（UDF v2.0格式）
- 包含多城市/多站点的污染物时序数据
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
            name="get_guangdong_regular_stations",
            description="Query Guangdong regional comparison data for air quality analysis - Context-Aware V2",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.1.0",
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
        不再进行本地正则解析，直接转发question给UQP接口。

        Args:
            context: 执行上下文
            question: 完整的自然语言查询问题（由 LLM 生成，直接发送给UQP接口）
            comparison_type: 对比类型 ("city" 城市级 | "station" 站点级)
            chart_title: 图表标题

        Returns:
            UDF v2.0格式的查询结果
        """
        logger.info(
            "regional_comparison_query_start",
            question=question,
            comparison_type=comparison_type,
            chart_title=chart_title,
            session_id=getattr(context, 'session_id', 'unknown')
        )

        try:
            # 直接使用question发送给UQP接口，完全依赖UQP的自然语言理解
            all_records = await self._query_pollutant_data_direct(
                question=question,
                comparison_type=comparison_type
            )

            if not all_records:
                return self._create_error_response("未查询到符合条件的监测数据", question)

            # 【调试】打印原始数据的前3条记录的 cityOrder 和 name 字段值
            for i, rec in enumerate(all_records[:3]):
                logger.info(
                    f"raw_record_{i}_debug",
                    cityOrder=rec.get("cityOrder"),
                    name=rec.get("name"),
                    o3=rec.get("o3"),
                    code=rec.get("code")
                )
            logger.info(
                "raw_data_sample",
                first_record_keys=list(all_records[0].keys())[:15] if all_records else [],
                second_record_keys=list(all_records[1].keys())[:15] if len(all_records) > 1 else []
            )

            # 数据标准化
            data_standardizer = get_data_standardizer()
            logger.info(
                "regional_comparison_standardization_start",
                raw_count=len(all_records),
                first_raw_keys=list(all_records[0].keys())[:15] if all_records else [],
                sample_raw_values={
                    k: all_records[0].get(k) for k in ['pM2_5', 'pM10', 'o3', 'aqi', 'co']
                    if k in all_records[0]
                }
            )
            standardized_records = data_standardizer.standardize(all_records)

            # 调试：打印标准化后的数据字段
            logger.info(
                "regional_comparison_data_standardized",
                raw_count=len(all_records),
                standardized_count=len(standardized_records),
                first_standardized_keys=list(standardized_records[0].keys())[:20] if standardized_records else [],
                has_measurements="measurements" in standardized_records[0] if standardized_records else False,
                measurements_content={
                    k: standardized_records[0].get(k)
                    for k in ['station_name', 'timestamp', 'PM2_5', 'PM10', 'measurements']
                    if k in standardized_records[0]
                } if standardized_records else {}
            )

            # 保存到上下文
            data_features = DataFeaturesExtractor.extract_features(
                standardized_records,
                schema_type="guangdong_stations"
            )

            # 从返回的数据中提取元数据（而不是从question解析）
            comp_type = comparison_type
            # 尝试从数据中推断污染物类型和城市信息
            pollutant = self._infer_pollutant_from_data(standardized_records)
            cities_from_data = self._extract_cities_from_data(standardized_records)
            
            # 根据对比类型生成schema名称
            schema_name = f"regional_{comp_type}_comparison"
            
            data_id = context.data_manager.save_data(
                data=standardized_records,
                schema=schema_name,
                metadata={
                    "question": question,
                    "source": "regional_comparison",
                    "data_type": f"regional_{comp_type}_comparison",
                    "schema_version": "v2.0",
                    "schema_type": schema_name,
                    "generator": "get_guangdong_regular_stations",
                    "scenario": f"regional_{comp_type}_comparison",
                    "comparison_type": comp_type,
                    "chart_title": chart_title,
                    "cities": cities_from_data,  # 从数据中提取，不依赖解析
                    "pollutant": pollutant,
                    "field_mapping_applied": True,
                    "field_mapping_info": data_standardizer.get_field_mapping_info(),
                    "data_features": data_features
                }
            )

            handle = context.data_manager.get_handle(data_id)

            logger.info(
                "regional_comparison_data_saved",
                data_id=data_id,
                record_count=handle.record_count,
                comparison_type=comp_type
            )

            # 生成摘要信息
            cities_summary = "、".join(cities_from_data[:5])  # 只显示前5个城市
            if len(cities_from_data) > 5:
                cities_summary += f"等{len(cities_from_data)}个城市"

            # 只有当成功推断出污染物类型时才显示
            if pollutant:  # pollutant 为 None 时表示无法推断
                summary = f"[OK] 成功获取{cities_summary}的{pollutant}数据共{handle.record_count}条"
            else:
                summary = f"[OK] 成功获取{cities_summary}的数据共{handle.record_count}条"

            # 生成数据样本（第一条记录，用于LLM快速了解数据结构）
            sample_record = standardized_records[0] if standardized_records else None
            if sample_record:
                # 提取关键字段用于样本展示
                sample_summary = {
                    "station_name": sample_record.get("station_name"),
                    "timestamp": sample_record.get("timestamp"),
                    "measurements": sample_record.get("measurements", {}),
                    "species_data": sample_record.get("species_data"),
                    "dimensions": sample_record.get("dimensions"),
                }
            else:
                sample_summary = None

            return {
                "status": "success",
                "success": True,
                "data": standardized_records,  # 返回完整数据
                "data_id": data_id,  # 顶层 data_id，供系统提取
                "metadata": {
                    "tool_name": "get_guangdong_regular_stations",
                    "registry_schema": schema_name,
                    "record_count": handle.record_count,
                    "question": question,
                    "cities": cities_from_data,
                    "pollutant": pollutant,
                    "comparison_type": comp_type,
                    "chart_title": chart_title,
                    "analysis_type": f"regional_{comp_type}_comparison",
                    "sample_record": sample_summary  # 添加数据样本
                },
                "summary": f"{summary}，已保存为 {data_id}。"
            }

        except Exception as e:
            logger.error(
                "regional_comparison_query_failed",
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

        【修改】只查询 O3_8h 8小时滑动平均数据，不再查询小时数据
        原因：跨长周期小时数据量巨大（1年×21城市×365天×24小时≈18万条），会导致API超时

        Args:
            question: LLM生成的自然语言查询问题
            comparison_type: 对比类型

        Returns:
            查询结果记录列表（O3_8h 8小时滑动平均数据）
        """
        url = "http://180.184.91.74:9091/api/uqp/query"

        logger.info(
            "direct_query_to_uqp",
            question=question,
            comparison_type=comparison_type
        )

        all_records = []

        # 【关键】直接使用原始question查询，UQP API支持多城市一次性查询
        # 不拆分城市，让UQP自己理解问题并返回多城市数据
        # 【重要】完全由LLM决策查询内容，代码不做任何自动追加

        try:
            # 直接使用原始 question，UQP 接口会自动理解并返回相应数据
            response = await http_client.post(
                url,
                json_data={"question": question},
                timeout=120
            )
            records = self._seek_records(response)
            if records:
                for record in records:
                    filtered_record = {
                        k: v for k, v in record.items()
                        if not k.endswith('_IAQI') and not k.endswith('_iaqi')
                    }
                    # 保留原始 code 字段作为 city_code，便于后续识别城市
                    if "code" in filtered_record and "city_code" not in filtered_record:
                        filtered_record["city_code"] = filtered_record["code"]
                    all_records.append(filtered_record)

                logger.info(
                    "uqp_query_success",
                    question=question,
                    records_count=len(records)
                )

        except Exception as e:
            logger.warning(
                "uqp_query_failed",
                question=question,
                error=str(e)
            )

        if all_records:
            logger.info(
                "uqp_query_complete",
                question=question,
                total_records=len(all_records)
            )
            return all_records
        else:
            logger.warning(
                "uqp_query_no_records",
                question=question
            )
            return []

    def _infer_pollutant_from_data(self, records: List[Dict[str, Any]]) -> Optional[str]:
        """
        从数据中推断污染物类型

        支持的数据格式：
        1. 顶层字段格式：{"PM2_5": 39.0, "O3": 143.0, ...}
        2. measurements 嵌套格式：{"measurements": {"PM2_5": 39.0, "O3": 143.0, ...}}
        3. original_fields.primary_pollutant 格式：{"original_fields": {"primary_pollutant": "O3_8H"}}

        Returns:
            成功推断返回污染物类型字符串（如"PM2.5"、"O3_8h"）
            无法推断返回 None
        """
        if not records:
            return None

        first_record = records[0]

        # 【优先级1】检查 original_fields.primary_pollutant（最准确的首要污染物标识）
        original_fields = first_record.get("original_fields", {})
        if isinstance(original_fields, dict) and "primary_pollutant" in original_fields:
            primary = original_fields["primary_pollutant"]
            logger.info(
                "pollutant_inferred_from_primary_pollutant",
                pollutant=primary,
                source="original_fields.primary_pollutant"
            )
            return primary

        # 【优先级2】检查 measurements 字段（标准化后的污染物数据）
        measurements = first_record.get("measurements", {})
        if isinstance(measurements, dict) and measurements:
            # 定义污染物优先级列表（按重要性和检测频率排序）
            # 注意：使用标准化的字段名（下划线格式，如 PM2_5）
            pollutant_priority = [
                ("PM2_5", "PM2.5"),
                ("O3_8h", "O3_8h"),
                ("O3", "O3"),
                ("PM10", "PM10"),
                ("NO2", "NO2"),
                ("SO2", "SO2"),
                ("CO", "CO"),
                ("AQI", "AQI")
            ]

            # 按优先级查找第一个存在的污染物
            for standard_name, display_name in pollutant_priority:
                if standard_name in measurements:
                    logger.info(
                        "pollutant_inferred_from_measurements",
                        pollutant=display_name,
                        detected_field=standard_name,
                        available_measurements=list(measurements.keys())
                    )
                    return display_name

            # 如果优先级列表都没有，返回 measurements 的第一个键
            first_key = next(iter(measurements.keys()))
            normalized = first_key.replace("_", ".")  # PM2_5 → PM2.5
            logger.info(
                "pollutant_inferred_from_first_measurement",
                pollutant=normalized,
                detected_field=first_key
            )
            return normalized

        # 【优先级3】检查顶层字段（兼容旧格式）
        # 【新增】优先检查O3_8h字段（8小时滑动平均）
        o3_8h_fields = ["O3_8h", "O3_8H", "O38H", "O38h", "臭氧8小时", "臭氧8小时平均", "O3-8h"]
        for field in o3_8h_fields:
            if field in first_record or any(field.lower() == k.lower() for k in first_record.keys()):
                logger.info(
                    "pollutant_inferred_from_top_level",
                    pollutant="O3_8h",
                    detected_field=field
                )
                return "O3_8h"

        # 扩展的污染物字段列表（中英文）
        pollutant_fields = [
            "PM2_5", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "AQI",  # 英文（含下划线格式）
            "PM25", "臭氧", "二氧化氮", "二氧化硫", "一氧化碳",  # 中文
            "臭氧(O3)", "PM2.5(细颗粒物)", "PM10(颗粒物)"  # 中文带括号
        ]

        for field in pollutant_fields:
            if field in first_record or any(field.lower() in k.lower() for k in first_record.keys()):
                normalized = field.replace("_", ".").replace("(", " (").replace(")", ")").split("(")[0].strip()
                logger.info(
                    "pollutant_inferred_from_top_level",
                    pollutant=normalized,
                    detected_field=field
                )
                return normalized

        # 【无法推断】返回 None，让调用方决定如何处理
        logger.warning(
            "pollutant_inference_failed",
            message="无法从数据中推断污染物类型",
            first_record_keys=list(first_record.keys())[:10],
            has_measurements="measurements" in first_record,
            has_original_fields="original_fields" in first_record
        )
        return None  # 返回 None 而非默认值，由摘要生成逻辑决定是否显示

    def _extract_cities_from_data(self, records: List[Dict[str, Any]]) -> List[str]:
        """从数据中提取城市列表"""
        cities = set()

        if not records:
            logger.warning("_extract_cities_from_data: records is empty")
            return []

        # 调试：打印第一条记录的字段
        first_record = records[0]
        logger.info(
            "_extract_cities_from_data_debug",
            first_record_keys=list(first_record.keys())[:15],
            city_order_value=first_record.get("cityOrder"),
            city_code_value=first_record.get("city_code"),
            city_value=first_record.get("city"),
            station_name=first_record.get("station_name"),
            name_value=first_record.get("name"),
            district_name=first_record.get("districtName") or first_record.get("district_name")
        )

        # 城市编码到名称的映射
        city_code_map = {
            "4401": "广州", "4402": "深圳", "4403": "珠海", "4404": "汕头",
            "4405": "佛山", "4406": "韶关", "4407": "湛江", "4408": "肇庆",
            "4409": "江门", "4412": "茂名", "4413": "惠州", "4414": "梅州",
            "4415": "汕尾", "4416": "河源", "4417": "阳江", "4418": "清远",
            "4419": "东莞", "4420": "中山", "4451": "潮州", "4452": "揭阳", "4453": "云浮",
        }

        for record in records:
            city = None

            # 1. 首先检查标准化后的 city 字段（非省级数据）
            city = record.get("city")
            if city and city not in ["广东省", None]:
                cities.add(str(city).replace("市", "").strip())
                continue

            # 2. 检查 city_code（标准化后）
            city_code = record.get("city_code")
            if city_code:
                city_name = city_code_map.get(str(city_code))
                if city_name:
                    cities.add(city_name)
                    continue

            # 3. 检查 cityOrder（原始字段）
            city_order = record.get("cityOrder")
            if city_order:
                city_name = city_code_map.get(str(city_order))
                if city_name:
                    cities.add(city_name)
                    continue

            # 4. 从站点名称推断城市（处理"广东省xx市"格式）
            station_name = record.get("station_name") or record.get("name", "")
            # 先去除"广东省"前缀
            clean_name = station_name.replace("广东省", "").strip()
            for city_name in city_code_map.values():
                if city_name in clean_name:
                    cities.add(city_name)
                    break
            else:
                # 如果站点名中没有城市名，尝试从区县级推断
                district_name = record.get("districtName") or record.get("district_name") or ""
                for city_name in city_code_map.values():
                    if city_name in district_name:
                        cities.add(city_name)
                        break

        logger.info(
            "_extract_cities_from_data_result",
            cities_count=len(cities),
            cities=list(cities)
        )

        return sorted(list(cities))

    async def _get_cities_with_neighbors(self, city_name: str, k: int = 4) -> List[str]:
        """
        获取目标城市及周边城市列表

        Args:
            city_name: 目标城市名
            k: 周边城市数量（3-5）

        Returns:
            城市列表（含目标城市）
        """
        try:
            # 调用station_api获取周边城市
            response = await station_api.get_nearby_cities(
                city_name=city_name,
                k=min(max(k, 3), 5),  # 限制3-5个
                station_type_id=1.0,  # 只获取国控站点
                fields="name,code,lat,lon,district"
            )

            cities = [city_name]  # 首先加入目标城市
            
            neighbors = response.get("neighbors", [])
            for neighbor in neighbors:
                neighbor_city = neighbor.get("city", "").replace("市", "")
                if neighbor_city and neighbor_city not in cities:
                    cities.append(neighbor_city)

            logger.info(
                "nearby_cities_fetched",
                target=city_name,
                neighbors_count=len(neighbors),
                cities=cities
            )

            return cities

        except Exception as e:
            logger.warning(
                "get_nearby_cities_failed",
                city_name=city_name,
                error=str(e)
            )
            # 降级：使用预定义的周边城市映射
            default_neighbors = {
                "广州": ["深圳", "佛山", "东莞", "惠州"],
                "深圳": ["广州", "东莞", "惠州", "香港"],
                "佛山": ["广州", "中山", "江门", "肇庆"],
                "东莞": ["广州", "深圳", "惠州", "佛山"],
                "惠州": ["深圳", "东莞", "广州", "河源"],
                "珠海": ["中山", "江门", "澳门", "佛山"],
                "中山": ["珠海", "佛山", "江门", "广州"],
                "江门": ["佛山", "中山", "珠海", "肇庆"],
                "肇庆": ["佛山", "广州", "云浮", "江门"],
                "揭阳": ["汕头", "潮州", "梅州", "汕尾"],
                "汕头": ["揭阳", "潮州", "梅州", "汕尾"],
                "潮州": ["汕头", "揭阳", "梅州", "福建"],
                "梅州": ["揭阳", "河源", "潮州", "汕头"],
            }
            neighbors = default_neighbors.get(city_name, ["深圳", "佛山", "东莞", "惠州"])
            return [city_name] + neighbors[:k]

    async def _get_cities_stations(
        self,
        cities: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取各城市的国控站点列表

        Args:
            cities: 城市列表

        Returns:
            {城市名: [站点信息列表]}
        """
        cities_stations = {}

        for city in cities:
            try:
                stations = await station_api.get_city_stations(
                    city_name=city,
                    station_type_id=1.0,  # 国控站点
                    fields="name,code,lat,lon,district,type_id"
                )
                cities_stations[city] = stations if stations else []
                
                logger.info(
                    "city_stations_fetched",
                    city=city,
                    stations_count=len(stations) if stations else 0
                )

            except Exception as e:
                logger.warning(
                    "get_city_stations_failed",
                    city=city,
                    error=str(e)
                )
                cities_stations[city] = []

        return cities_stations


    async def _query_pollutant_data(
        self,
        question: str,
        query_info: Dict[str, Any],
        cities_stations: Dict[str, List[Dict[str, Any]]],
        comparison_type: str = "city"
    ) -> List[Dict[str, Any]]:
        """
        查询各城市/站点的污染物时序数据

        Args:
            question: LLM 生成的原始查询问题
            query_info: 解析后的查询信息（包含 pollutant, start_time, end_time, granularity 等）
            cities_stations: {城市: [站点列表]}
            comparison_type: "city" 城市级对比 | "station" 站点级对比

        Returns:
            所有记录列表
        """
        all_records = []
        url = "http://180.184.91.74:9091/api/uqp/query"
        cities = list(cities_stations.keys())
        pollutant = query_info.get("pollutant", "O3")
        start_time = query_info.get("start_time", "")
        end_time = query_info.get("end_time", "")
        granularity_cn = query_info.get("granularity_cn", "日")  # 直接使用解析好的粒度中文

        # 站点级对比：直接查询各站点数据，跳过城市级查询
        if comparison_type == "station":
            logger.info(
                "station_comparison_direct_query",
                cities_count=len(cities),
                pollutant=pollutant,
                granularity_cn=granularity_cn
            )
            
            for city, stations in cities_stations.items():
                if not stations:
                    continue

                # 获取所有站点名称
                station_names = [s.get("站点名称", s.get("name", "")) for s in stations]
                station_names = [n for n in station_names if n]

                if station_names:
                    stations_str = "、".join(station_names)
                    # 使用原始 question 的粒度格式构造查询
                    station_question = f"查询{stations_str}站点{start_time}至{end_time}的{pollutant}站点{granularity_cn}数据"

                    try:
                        response = await http_client.post(
                            url,
                            json_data={"question": station_question},
                            timeout=120  # 延长超时时间为120秒，支持大范围查询
                        )
                        records = self._seek_records(response)
                        if records:
                            # 添加城市标识
                            for record in records:
                                record["city"] = city
                            all_records.extend(records)

                            logger.info(
                                "station_hourly_query_success",
                                city=city,
                                stations_count=len(station_names),
                                records_count=len(records)
                            )

                    except Exception as e:
                        logger.warning(
                            "station_hourly_query_failed",
                            city=city,
                            error=str(e)
                        )
            
            return all_records

        # 城市级对比：直接使用原始 question 查询城市数据
        # 对于报告生成场景，直接使用 LLM 生成的完整查询问题，不需要重新组装
        logger.info(
            "city_comparison_query",
            question=question,
            cities_count=len(cities),
            pollutant=pollutant,
            granularity_cn=granularity_cn
        )

        try:
            # 直接使用原始 question，UQP 接口会自动理解城市级查询
            response = await http_client.post(
                url,
                json_data={"question": question},
                timeout=120  # 延长超时时间为120秒，支持大范围查询
            )
            records = self._seek_records(response)
            
            if records:
                # 为记录添加城市标识（如果返回数据中没有）
                for record in records:
                    if "city" not in record and "城市" not in record:
                        station_name = record.get("station_name") or record.get("站点名称", "")
                        for city in cities:
                            if city in station_name:
                                record["city"] = city
                                break
                
                all_records.extend(records)

                logger.info(
                    "city_query_success",
                    question=question,
                    records_count=len(records)
                )

        except Exception as e:
            logger.error(
                "city_query_failed",
                question=question,
                error=str(e)
            )

        # 城市级查询直接返回结果，不进行站点级补充（站点数据不能替代城市数据）
        return all_records

    def _seek_records(self, payload: Any) -> Optional[List[Dict[str, Any]]]:
        """
        从UQP响应中提取记录列表

        支持多种响应结构：
        - data.result (UQP标准结构)
        - data.data.result (嵌套结构)
        - data (直接列表)
        - result (直接列表)
        - results (多查询结果)
        """
        # 调试日志：记录响应结构
        if isinstance(payload, dict):
            logger.info(
                "_seek_records_debug",
                response_keys=list(payload.keys())[:15],
                has_result="result" in payload,
                has_data="data" in payload,
                has_results="results" in payload
            )
        elif isinstance(payload, list):
            logger.info("_seek_records_debug", response_type="list", length=len(payload))

        if isinstance(payload, list):
            for item in payload:
                nested = self._seek_records(item)
                if nested:
                    return nested
            return self._ensure_dict_list(payload)

        if isinstance(payload, dict):
            # === 优先处理 UQP 标准结构: data.result ===
            if "result" in payload:
                result = payload["result"]
                if isinstance(result, list):
                    return result
                elif isinstance(result, dict):
                    # data.result 结构
                    if "list" in result:
                        return result["list"]
                    elif "data" in result:
                        nested = result["data"]
                        if isinstance(nested, list):
                            return nested
                        elif isinstance(nested, dict) and "list" in nested:
                            return nested["list"]

            # === 处理 data 字段 ===
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

            # === 处理多查询结构: results ===
            if "results" in payload and isinstance(payload["results"], list):
                all_records = []
                for result_item in payload["results"]:
                    if isinstance(result_item, dict):
                        # results[x].data 结构
                        if "data" in result_item:
                            records = self._seek_records(result_item["data"])
                            if records:
                                all_records.extend(records)
                        # results[x].result 结构
                        elif "result" in result_item:
                            result = result_item["result"]
                            if isinstance(result, list):
                                all_records.extend(result)
                return all_records if all_records else None

            # === 查找其他可能的记录字段 ===
            for key in ("data", "result", "results", "stations", "value", "payload"):
                value = payload.get(key)
                if isinstance(value, list):
                    normalised = self._ensure_dict_list(value)
                    if normalised:
                        return normalised

            # === 递归查找嵌套结构 ===
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
                "tool_name": "get_guangdong_regular_stations",
                "error_type": "execution_failed",
                "question": question
            },
            "summary": f"[FAIL] 区域对比数据查询失败: {error_msg[:100]}"
        }
