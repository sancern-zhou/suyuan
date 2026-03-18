# 新旧标准对比功能实现方案

## 1. 需求澄清

### 1.1 数据来源
- **旧标准数据**：直接从`query_gd_suncere_report`统计接口获取，不重新计算
- **新标准数据**：基于旧标准数据，只重新计算PM2.5和PM10的IAQI（断点不同），其他参数复用
- **统计数据**：并发查询`query_gd_suncere_report`接口获取

### 1.2 并发查询接口
1. **query_gd_suncere_city_day**：获取城市日数据（浓度值、旧标准IAQI等）
2. **query_gd_suncere_report**：获取统计数据（任意时段综合统计）

### 1.3 query_gd_suncere_report返回的统计字段
| 字段 | 说明 | 备注 |
|------|------|------|
| compositeIndex | 旧标准综合指数 | 直接使用 |
| overDays | 旧标准超标天数 | 直接使用 |
| overRate | 旧标准超标率 | 直接使用 |
| rank | 旧标准综合指数排名 | 直接使用 |
| validDays | 有效天数 | 新旧标准一致 |
| pM2_5_Rank | 旧标准PM2.5排名 | 直接使用 |
| SO2, NO2, PM10, CO, PM2_5, NO, NOx, o3_8H | 统计浓度值 | 新旧标准无变化 |

### 1.4 新旧标准差异
1. **PM2.5断点**：IAQI=50时35→30，IAQI=100时75→60
2. **PM10断点**：IAQI=100时150→120
3. **新标准综合指数**：带权重算法（PM2.5权重3，O3权重2，NO2权重2，其他权重1）
4. **其他参数**：SO2、NO2、O3、CO、O3_8h的IAQI断点值无变化，直接复用旧标准数据

## 2. 数据流程

```
用户请求查询城市日数据（含新旧标准对比）
    ↓
并发查询（asyncio.gather）
├── query_gd_suncere_city_day → 日报数据（浓度值、旧标准IAQI）
└── query_gd_suncere_report → 统计数据（旧标准综合指数、超标天数等）
    ↓
数据处理
├── 从日报数据提取每条记录的旧标准数据
├── 计算每条记录的新标准IAQI（仅PM2.5和PM10）
├── 计算每条记录的新标准综合指数（带权重）
├── 计算每条记录的对比字段（变化量、变化率）
└── 计算时段统计摘要（基于统计数据）
    ↓
返回UDF v2.0格式数据
```

## 3. 文件结构

### 3.1 新增文件
```
backend/app/utils/
├── aqi_standard_calculator.py      # AQI标准计算器（新旧标准IAQI计算）
└── composite_index_calculator.py   # 综合指数计算器（新标准权重算法）

backend/app/tools/query/query_gd_suncere/
└── standard_comparison_mixin.py    # 标准对比功能混入类
```

### 3.2 修改文件
```
backend/app/tools/query/query_gd_suncere/
├── tool.py                          # 扩展query_city_day_data方法
└── tool_wrapper.py                  # 更新工具描述
```

## 4. 核心模块设计

### 4.1 AQI标准计算器（aqi_standard_calculator.py）

```python
"""
AQI标准计算器
支持新旧标准的IAQI计算
"""
from typing import Dict, Optional
from enum import Enum

class StandardType(Enum):
    """标准类型"""
    OLD = "old"   # 旧标准 HJ 633-2011
    NEW = "new"   # 新标准 HJ 633-2024

# IAQI断点配置
IAQI_BREAKPOINTS = {
    StandardType.OLD: {
        'PM2_5': {
            'breakpoints': [0, 35, 75, 115, 150, 250, 350, 500],
            'iaqi_values': [0, 50, 100, 150, 200, 300, 400, 500]
        },
        'PM10': {
            'breakpoints': [0, 50, 150, 250, 350, 420, 500, 600],
            'iaqi_values': [0, 50, 100, 150, 200, 300, 400, 500]
        }
    },
    StandardType.NEW: {
        'PM2_5': {
            'breakpoints': [0, 30, 60, 115, 150, 250, 350, 500],
            'iaqi_values': [0, 50, 100, 150, 200, 300, 400, 500]
        },
        'PM10': {
            'breakpoints': [0, 50, 120, 250, 350, 420, 500, 600],
            'iaqi_values': [0, 50, 100, 150, 200, 300, 400, 500]
        }
    }
}

def calculate_iaqi(
    concentration: float,
    pollutant: str,
    standard_type: StandardType = StandardType.NEW
) -> float:
    """
    计算IAQI值

    Args:
        concentration: 污染物浓度
        pollutant: 污染物类型（PM2_5或PM10）
        standard_type: 标准类型

    Returns:
        IAQI值
    """
    config = IAQI_BREAKPOINTS[standard_type][pollutant]
    breakpoints = config['breakpoints']
    iaqi_values = config['iaqi_values']

    # 找到浓度所在的区间
    for i in range(len(breakpoints) - 1):
        if breakpoints[i] <= concentration <= breakpoints[i + 1]:
            bp_lo = breakpoints[i]
            bp_hi = breakpoints[i + 1]
            iaqi_lo = iaqi_values[i]
            iaqi_hi = iaqi_values[i + 1]

            # 线性插值计算IAQI
            iaqi = ((iaqi_hi - iaqi_lo) / (bp_hi - bp_lo)) * (concentration - bp_lo) + iaqi_lo
            return round(iaqi, 1)

    # 超出范围的处理
    if concentration > breakpoints[-1]:
        return iaqi_values[-1]
    return iaqi_values[0]
```

### 4.2 综合指数计算器（composite_index_calculator.py）

```python
"""
综合指数计算器
支持新标准带权重的综合指数计算
"""
from typing import Dict

# 新标准权重配置
NEW_STANDARD_WEIGHTS = {
    'PM2_5': 3,
    'O3': 2,
    'NO2': 2,
    'SO2': 1,
    'CO': 1,
    'PM10': 1,
    'O3_8h': 2  # O3 8小时平均
}

def calculate_composite_index_new(
    iaqi_values: Dict[str, float]
) -> float:
    """
    计算新标准综合指数

    公式：
    Imax = MAX(ωi · Ii)
    Isum = Σ ωi · Ii
    综合指数 = MAX(Imax, Isum)

    Args:
        iaqi_values: 各污染物IAQI值
                    需要：PM2_5_IAQI, PM10_IAQI, SO2_IAQI, NO2_IAQI, CO_IAQI, O3_IAQI, O3_8h_IAQI

    Returns:
        新标准综合指数
    """
    weighted_iaqis = []
    weight_mapping = {
        'PM2_5_IAQI': 'PM2_5',
        'PM10_IAQI': 'PM10',
        'SO2_IAQI': 'SO2',
        'NO2_IAQI': 'NO2',
        'CO_IAQI': 'CO',
        'O3_IAQI': 'O3',
        'O3_8h_IAQI': 'O3_8h'
    }

    for iaqi_field, pollutant in weight_mapping.items():
        if iaqi_field in iaqi_values and iaqi_values[iaqi_field] is not None:
            weight = NEW_STANDARD_WEIGHTS[pollutant]
            weighted_iaqi = iaqi_values[iaqi_field] * weight
            weighted_iaqis.append(weighted_iaqi)

    if not weighted_iaqis:
        return 0.0

    imax = max(weighted_iaqis)
    isum = sum(weighted_iaqis)

    return max(imax, isum)
```

### 4.3 标准对比混入类（standard_comparison_mixin.py）

```python
"""
标准对比功能混入类
为查询工具添加新旧标准对比功能
"""
import asyncio
from typing import Dict, Any, List, Optional
from app.agent.context.execution_context import ExecutionContext
from app.utils.aqi_standard_calculator import calculate_iaqi, StandardType
from app.utils.composite_index_calculator import calculate_composite_index_new

class StandardComparisonMixin:
    """标准对比功能混入类"""

    @staticmethod
    async def query_with_comparison(
        cities: List[str],
        start_date: str,
        end_date: str,
        context: ExecutionContext,
        enable_comparison: bool = True
    ) -> Dict[str, Any]:
        """
        查询城市日数据（含新旧标准对比）

        Args:
            cities: 城市列表
            start_date: 开始日期
            end_date: 结束日期
            context: 执行上下文
            enable_comparison: 是否启用对比

        Returns:
            查询结果（含新旧标准对比）
        """
        if not enable_comparison:
            # 不启用对比，直接查询日报数据
            return await StandardComparisonMixin._query_daily_data_only(
                cities, start_date, end_date, context
            )

        # 并发查询日报数据和统计数据
        daily_task = StandardComparisonMixin._query_daily_data(
            cities, start_date, end_date, context
        )
        report_task = StandardComparisonMixin._query_report_data(
            cities, start_date, end_date
        )

        daily_result, report_result = await asyncio.gather(
            daily_task,
            report_task,
            return_exceptions=True
        )

        # 处理异常
        if isinstance(daily_result, Exception):
            return StandardComparisonMixin._create_error_response(str(daily_result))

        # 增强数据（添加新标准字段）
        enhanced_records = StandardComparisonMixin._enhance_records_with_new_standard(
            daily_result.get('data', [])
        )

        # 计算统计摘要
        summary = StandardComparisonMixin._calculate_comparison_summary(
            enhanced_records,
            report_result if not isinstance(report_result, Exception) else None
        )

        # 返回结果
        return {
            "status": "success",
            "success": True,
            "data": enhanced_records[:50],
            "metadata": {
                "tool_name": "query_gd_suncere_city_day",
                "data_id": daily_result.get("metadata", {}).get("data_id"),
                "total_records": len(enhanced_records),
                "returned_records": min(50, len(enhanced_records)),
                "cities": cities,
                "date_range": f"{start_date} to {end_date}",
                "schema_version": "v2.0",
                "comparison_enabled": True,
                "source": "gd_suncere_api"
            },
            "summary": summary
        }

    @staticmethod
    def _enhance_records_with_new_standard(
        records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        为记录添加新标准字段

        对每条记录：
        1. 计算新标准PM2.5_IAQI和PM10_IAQI
        2. 计算新标准综合指数
        3. 计算对比字段（变化量、变化率）
        4. 判定是否超标
        """
        enhanced_records = []

        for record in records:
            enhanced_record = record.copy()
            measurements = record.get('measurements', {})

            # 提取旧标准数据
            old_pm25_iaqi = measurements.get('PM2_5_IAQI', 0)
            old_pm10_iaqi = measurements.get('PM10_IAQI', 0)
            old_aqi = measurements.get('AQI', 0)  # 旧标准AQI即综合指数

            # 提取浓度值
            pm25_concentration = measurements.get('PM2_5', 0)
            pm10_concentration = measurements.get('PM10', 0)

            # 计算新标准IAQI
            new_pm25_iaqi = calculate_iaqi(pm25_concentration, 'PM2_5', StandardType.NEW)
            new_pm10_iaqi = calculate_iaqi(pm10_concentration, 'PM10', StandardType.NEW)

            # 计算新标准综合指数
            new_iaqi_values = {
                'PM2_5_IAQI': new_pm25_iaqi,
                'PM10_IAQI': new_pm10_iaqi,
                'SO2_IAQI': measurements.get('SO2_IAQI', 0),
                'NO2_IAQI': measurements.get('NO2_IAQI', 0),
                'CO_IAQI': measurements.get('CO_IAQI', 0),
                'O3_IAQI': measurements.get('O3_IAQI', 0),
                'O3_8h_IAQI': measurements.get('species_data', {}).get('o3_8H_IAQI', measurements.get('O3_8h_IAQI', 0))
            }
            new_composite_index = calculate_composite_index_new(new_iaqi_values)

            # 添加新标准字段到measurements
            measurements['NEW_PM2_5_IAQI'] = new_pm25_iaqi
            measurements['NEW_PM10_IAQI'] = new_pm10_iaqi
            measurements['NEW_COMPOSITE_INDEX'] = new_composite_index

            # 计算对比字段
            measurements['PM2_5_IAQI_CHANGE'] = new_pm25_iaqi - old_pm25_iaqi
            measurements['PM10_IAQI_CHANGE'] = new_pm10_iaqi - old_pm10_iaqi
            measurements['COMPOSITE_INDEX_CHANGE'] = new_composite_index - old_aqi

            if old_aqi > 0:
                measurements['COMPOSITE_INDEX_CHANGE_RATE'] = (
                    (new_composite_index - old_aqi) / old_aqi * 100
                )
            else:
                measurements['COMPOSITE_INDEX_CHANGE_RATE'] = 0.0

            # 判定是否超标（AQI > 100）
            measurements['OLD_EXCEEDED'] = old_aqi > 100
            measurements['NEW_EXCEEDED'] = new_composite_index > 100

            enhanced_record['measurements'] = measurements
            enhanced_records.append(enhanced_record)

        return enhanced_records

    @staticmethod
    def _calculate_comparison_summary(
        records: List[Dict[str, Any]],
        report_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        计算对比摘要

        包含：
        1. 从query_gd_suncere_report获取的旧标准统计数据
        2. 基于记录计算的新标准统计数据
        3. 对比数据（变化量、变化率）
        """
        if not records:
            return {}

        total_days = len(records)

        # 计算新标准统计
        new_exceed_days = sum(
            1 for r in records
            if r.get('measurements', {}).get('NEW_EXCEEDED', False)
        )
        new_good_days = total_days - new_exceed_days
        new_composite_avg = sum(
            r.get('measurements', {}).get('NEW_COMPOSITE_INDEX', 0)
            for r in records
        ) / total_days if total_days > 0 else 0

        # 从report_data获取旧标准统计数据
        old_stats = {}
        if report_data and report_data.get('success'):
            report_records = report_data.get('data', [])
            if report_records:
                first_record = report_records[0]
                old_stats = {
                    'composite_index': first_record.get('compositeIndex', 0),
                    'exceed_days': first_record.get('overDays', 0),
                    'exceed_rate': first_record.get('overRate', 0),
                    'rank': first_record.get('rank', 0),
                    'valid_days': first_record.get('validDays', 0),
                    'pm2_5_rank': first_record.get('pM2_5_Rank', 0)
                }

                # 添加统计浓度值
                for pollutant in ['SO2', 'NO2', 'PM10', 'CO', 'PM2_5', 'NO', 'NOx']:
                    key = pollutant.lower() if pollutant in ['SO2', 'NO2', 'CO'] else f'pM{pollutant.split("_")[1]}_' if pollutant.startswith('PM') else pollutant
                    if key in first_record:
                        old_stats[f'{pollut}_avg'] = first_record[key]

        # 如果没有report数据，从records计算旧标准统计
        if not old_stats:
            old_exceed_days = sum(
                1 for r in records
                if r.get('measurements', {}).get('OLD_EXCEEDED', False)
            )
            old_good_days = total_days - old_exceed_days
            old_composite_avg = sum(
                r.get('measurements', {}).get('AQI', 0)
                for r in records
            ) / total_days if total_days > 0 else 0

            old_stats = {
                'composite_index': old_composite_avg,
                'exceed_days': old_exceed_days,
                'exceed_rate': old_exceed_days / total_days if total_days > 0 else 0,
                'good_days': old_good_days
            }

        # 计算对比
        comparison = {
            'composite_index_change': new_composite_avg - old_stats.get('composite_index', 0),
            'composite_index_change_rate': (
                (new_composite_avg - old_stats.get('composite_index', 0)) /
                old_stats.get('composite_index', 1) * 100
            ) if old_stats.get('composite_index', 0) > 0 else 0,
            'exceed_days_change': new_exceed_days - old_stats.get('exceed_days', 0),
            'compliance_rate_change': (
                (new_good_days - old_stats.get('good_days', total_days - old_stats.get('exceed_days', 0))) /
                total_days * 100
            ) if total_days > 0 else 0
        }

        return {
            'total_days': total_days,
            'old_standard': old_stats,
            'new_standard': {
                'composite_index': new_composite_avg,
                'exceed_days': new_exceed_days,
                'good_days': new_good_days,
                'compliance_rate': new_good_days / total_days if total_days > 0 else 0
            },
            'comparison': comparison,
            'statistical_concentrations': {
                pollutant: old_stats.get(f'{pollutant}_avg', 0)
                for pollutant in ['SO2', 'NO2', 'PM10', 'CO', 'PM2_5', 'NO', 'NOx', 'O3_8h']
            }
        }
```

## 5. 工具扩展（tool.py）

```python
# 在QueryGDSuncereDataTool类中添加方法

@classmethod
async def query_city_day_data_with_comparison(
    cls,
    cities: List[str],
    start_date: str,
    end_date: str,
    context: ExecutionContext,
    enable_comparison: bool = True
) -> Dict[str, Any]:
    """
    查询城市日报数据（含新旧标准对比）

    Args:
        cities: 城市名称列表
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        context: 执行上下文
        enable_comparison: 是否启用新旧标准对比

    Returns:
        查询结果（含新旧标准对比）
    """
    from app.tools.query.query_gd_suncere.standard_comparison_mixin import StandardComparisonMixin

    return await StandardComparisonMixin.query_with_comparison(
        cities=cities,
        start_date=start_date,
        end_date=end_date,
        context=context,
        enable_comparison=enable_comparison
    )
```

## 6. 工具包装器更新（tool_wrapper.py）

```python
class QueryGDSuncereCityDayTool(LLMTool):
    def __init__(self):
        function_schema = {
            "name": "query_gd_suncere_city_day",
            "description": """
查询广东省城市日报空气质量数据（支持新旧标准对比）。

【核心功能】
- 查询城市日报数据（PM2.5, PM10, SO2, NO2, CO, O3等）
- 支持新旧标准对比（2024新标准vs旧标准）
- 返回新旧两套IAQI和综合指数
- 并发查询统计数据（浓度统计、超标天数、排名等）
- 提供统计摘要（超标天数、优良天数、达标率、变化率）

【新旧标准差异】
- PM2.5断点变化：IAQI=50时，旧35μg/m³→新30μg/m³；IAQI=100时，旧75→新60
- PM10断点变化：IAQI=100时，旧150μg/m³→新120μg/m³
- 新标准综合指数：PM2.5权重3，O3权重2，NO2权重2，其他权重1
- 旧标准综合指数：直接从统计接口获取，不重新计算

【输入参数】
- cities: 城市名称列表
- start_date: 开始日期 (YYYY-MM-DD)
- end_date: 结束日期 (YYYY-MM-DD)
- enable_comparison: 是否计算新旧标准对比（默认True）

【返回数据】
每条记录包含：
- 旧标准数据（接口返回）：PM2_5_IAQI, PM10_IAQI, AQI（旧标准综合指数）
- 新标准数据（计算得到）：NEW_PM2_5_IAQI, NEW_PM10_IAQI, NEW_COMPOSITE_INDEX
- 对比数据：PM2_5_IAQI_CHANGE, COMPOSITE_INDEX_CHANGE, COMPOSITE_INDEX_CHANGE_RATE
- 超标判定：OLD_EXCEEDED, NEW_EXCEEDED

统计摘要包含：
- 旧标准统计（从统计接口）：compositeIndex, overDays, overRate, rank, validDays, pM2_5_Rank
- 新标准统计（基于记录计算）：composite_index, exceed_days, good_days, compliance_rate
- 对比数据：composite_index_change, composite_index_change_rate, exceed_days_change
- 统计浓度值：SO2, NO2, PM10, CO, PM2_5, NO, NOx, O3_8h的平均浓度
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式 YYYY-MM-DD"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期，格式 YYYY-MM-DD"
                    },
                    "enable_comparison": {
                        "type": "boolean",
                        "description": "是否计算新旧标准对比（默认True）",
                        "default": True
                    }
                },
                "required": ["cities", "start_date", "end_date"]
            }
        }

        super().__init__(
            name="query_gd_suncere_city_day",
            description="Query Guangdong city daily air quality data with standard comparison",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.0.0",  # 升级版本号
            requires_context=True
        )

    async def execute(
        self,
        context: ExecutionContext,
        cities: List[str],
        start_date: str,
        end_date: str,
        enable_comparison: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """执行查询"""
        from app.tools.query.query_gd_suncere.tool import QueryGDSuncereDataTool

        # 如果启用对比，使用新方法
        if enable_comparison:
            return await QueryGDSuncereDataTool.query_city_day_data_with_comparison(
                cities=cities,
                start_date=start_date,
                end_date=end_date,
                context=context,
                enable_comparison=True
            )

        # 否则使用原有方法
        return QueryGDSuncereDataTool.query_city_day_data(
            cities=cities,
            start_date=start_date,
            end_date=end_date,
            context=context
        )
```

## 7. 实施步骤

### 阶段1：核心计算模块（1-2天）
1. 创建`aqi_standard_calculator.py`：实现新旧标准IAQI计算
2. 创建`composite_index_calculator.py`：实现新标准综合指数计算
3. 单元测试：验证计算准确性

### 阶段2：对比功能模块（2-3天）
1. 创建`standard_comparison_mixin.py`：实现数据增强和统计摘要
2. 实现`_enhance_records_with_new_standard`方法
3. 实现`_calculate_comparison_summary`方法
4. 集成测试：验证数据增强和统计计算

### 阶段3：工具集成（1-2天）
1. 扩展`QueryGDSuncereDataTool.query_city_day_data_with_comparison`方法
2. 更新`QueryGDSuncereCityDayTool`工具包装器
3. 实现并发查询逻辑
4. 端到端测试

### 阶段4：测试验证（1-2天）
1. 单元测试：计算器准确性
2. 集成测试：并发查询和数据增强
3. 验证测试：与官方结果对比
4. 性能测试：响应时间<5秒

## 8. 成功标准

1. **准确性**：新标准计算结果与官方结果一致（误差<1%）
2. **完整性**：支持所有六项污染物的计算，返回完整的对比数据
3. **易用性**：LLM能正确识别对比需求并调用功能
4. **性能**：并发查询不影响响应速度（<5秒）
5. **兼容性**：向后兼容，不影响现有查询功能
