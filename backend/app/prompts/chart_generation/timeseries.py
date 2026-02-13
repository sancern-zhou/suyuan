"""
TimeseriesPrompt - 时序图专用提示词
"""

from typing import Dict, Any, Optional
from .base import BaseChartPrompt


class TimeseriesPrompt(BaseChartPrompt):
    """
    时序图专用Prompt

    适用场景：展示多系列时间序列数据
    """

    @property
    def chart_type(self) -> str:
        return "timeseries"

    def build_prompt(
        self,
        data: Dict[str, Any],
        title: Optional[str],
        **kwargs
    ) -> str:
        data_sample = self.format_data_sample(data, max_length=2500)

        prompt = f"""
{self.get_base_context()}

# 任务：生成时序图（Timeseries Chart）

## 数据样本
```json
{data_sample}
```

## 需求
- 标题: {title or '时序对比图'}

## 时序图特定规范

### 数据结构要求
时序图的data字段必须包含x（时间轴）和series（系列数组）：
```json
{{
  "x": ["2025-01-01 00:00", "2025-01-01 01:00", ...],  // 时间轴
  "series": [
    {{
      "name": "系列1名称",
      "data": [数值1, 数值2, ...],
      "unit": "单位（可选）"
    }},
    {{
      "name": "系列2名称",
      "data": [数值1, 数值2, ...],
      "unit": "单位（可选）"
    }}
  ]
}}
```

### 数据处理规则
1. **识别时间字段**: time/timestamp/date/datetime等
2. **识别系列字段**: 不同污染物/气象要素/站点等
3. **时间格式统一**: 使用ISO 8601格式（YYYY-MM-DD HH:mm:ss）
4. **数据对齐**: 确保所有series的data长度与x长度一致
5. **缺失值处理**: 缺失值可用null表示

### 常见数据格式转换

**格式1: 宽表格式**
输入:
```json
[
  {{"time": "2025-01-01 00:00", "O3": 45.2, "PM2.5": 32.1}},
  {{"time": "2025-01-01 01:00", "O3": 48.5, "PM2.5": 30.5}},
  ...
]
```
输出:
```json
{{
  "x": ["2025-01-01 00:00", "2025-01-01 01:00"],
  "series": [
    {{"name": "O3", "data": [45.2, 48.5], "unit": "μg/m³"}},
    {{"name": "PM2.5", "data": [32.1, 30.5], "unit": "μg/m³"}}
  ]
}}
```

**格式2: 长表格式**
输入:
```json
[
  {{"time": "2025-01-01 00:00", "pollutant": "O3", "value": 45.2}},
  {{"time": "2025-01-01 00:00", "pollutant": "PM2.5", "value": 32.1}},
  ...
]
```
输出: 按pollutant分组，每个pollutant成为一个series

{self.get_examples()}

### 输出示例（完整）
```json
{{
  "id": "timeseries_2025",
  "type": "timeseries",
  "title": "{title or '时序对比图'}",
  "data": {{
    "x": ["2025-01-01 00:00", "2025-01-01 01:00", "2025-01-01 02:00"],
    "series": [
      {{
        "name": "O3",
        "data": [45.2, 48.5, 52.1],
        "unit": "μg/m³"
      }},
      {{
        "name": "PM2.5",
        "data": [32.1, 30.5, 28.3],
        "unit": "μg/m³"
      }}
    ]
  }},
  "meta": {{
    "schema_version": "3.1",
    "generator": "llm_generated",
    "data_source": "generate_chart_llm",
    "record_count": 3,
    "time_range": "2025-01-01 00:00 ~ 2025-01-01 02:00"
  }}
}}
```

# 最佳实践
1. 时间格式统一且清晰
2. 系列名称简洁（避免过长）
3. 如果系列过多（>10），考虑只展示主要系列
4. 为每个series添加unit（如果单位不同）
5. 在meta中记录时间范围

请直接返回JSON（不要markdown代码块）。
        """.strip()

        return prompt

    def get_examples(self) -> str:
        """获取时序图示例"""
        return """
### 实际案例示例

**案例1**: 多污染物24小时趋势
- 输入数据: O3、PM2.5、NO2的24小时逐时浓度
- 生成结果: 3条曲线展示各污染物时间变化
- 特点: 清晰展示污染物日变化规律

**案例2**: 多站点对比
- 输入数据: 5个站点的PM2.5小时数据
- 生成结果: 5条曲线对比站点间差异
- 特点: 识别空间分布特征
        """.strip()
