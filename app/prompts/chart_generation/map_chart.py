"""
MapPrompt - 地图专用提示词
"""

from typing import Dict, Any, Optional
from .base import BaseChartPrompt


class MapPrompt(BaseChartPrompt):
    """
    地图专用Prompt

    适用场景：展示地理分布、站点位置
    """

    @property
    def chart_type(self) -> str:
        return "map"

    def build_prompt(
        self,
        data: Dict[str, Any],
        title: Optional[str],
        **kwargs
    ) -> str:
        data_sample = self.format_data_sample(data, max_length=2500)

        prompt = f"""
{self.get_base_context()}

# 任务：生成地图（Map Chart - 高德地图）

## 数据样本
```json
{data_sample}
```

## 需求
- 标题: {title or '站点分布地图'}

## 地图特定规范

### 数据结构要求
地图的data字段必须包含：
```json
{{
  "map_center": {{
    "lng": 114.05,  // 地图中心经度
    "lat": 22.54    // 地图中心纬度
  }},
  "zoom": 12,       // 缩放级别（3-18）
  "layers": [
    {{
      "type": "marker",  // 图层类型（marker/heatmap/polygon）
      "data": [
        {{
          "lng": 114.05,
          "lat": 22.54,
          "name": "站点名称",
          "value": 35.2,         // 可选：数值
          "pollutant": "PM2.5",  // 可选：污染物类型
          "industry": "化工",    // 可选：行业类型
          "distance": 1.2        // 可选：距离（km）
        }},
        ...
      ],
      "visible": true
    }}
  ]
}}
```

### 数据处理规则
1. **识别坐标字段**: longitude/lng 和 latitude/lat
2. **计算地图中心**: 如果未指定，取所有点的平均坐标
3. **智能缩放级别**:
   - 单点: zoom=15
   - 2-5个点: zoom=13
   - 5-20个点: zoom=12
   - 20+个点: zoom=11
4. **标记点信息**: name（必需）、value/pollutant/industry（可选）

### 常见数据格式转换

**格式1: 站点列表**
输入:
```json
[
  {{"station_name": "A站", "longitude": 114.05, "latitude": 22.54, "PM2.5": 35.2}},
  {{"station_name": "B站", "longitude": 114.06, "latitude": 22.55, "PM2.5": 42.1}},
  ...
]
```
输出:
```json
{{
  "map_center": {{"lng": 114.055, "lat": 22.545}},
  "zoom": 13,
  "layers": [
    {{
      "type": "marker",
      "data": [
        {{"lng": 114.05, "lat": 22.54, "name": "A站", "value": 35.2}},
        {{"lng": 114.06, "lat": 22.55, "name": "B站", "value": 42.1}}
      ],
      "visible": true
    }}
  ]
}}
```

**格式2: 企业位置**
输入:
```json
[
  {{"company": "XX化工", "lng": 114.05, "lat": 22.54, "industry": "化工", "distance": 1.2}},
  ...
]
```

{self.get_examples()}

### 输出示例（完整）
```json
{{
  "id": "map_2025",
  "type": "map",
  "title": "{title or '站点分布地图'}",
  "data": {{
    "map_center": {{
      "lng": 114.05,
      "lat": 22.54
    }},
    "zoom": 12,
    "layers": [
      {{
        "type": "marker",
        "data": [
          {{
            "lng": 114.05,
            "lat": 22.54,
            "name": "监测站点A",
            "value": 35.2,
            "pollutant": "PM2.5"
          }},
          {{
            "lng": 114.06,
            "lat": 22.55,
            "name": "监测站点B",
            "value": 42.1,
            "pollutant": "PM2.5"
          }}
        ],
        "visible": true
      }}
    ]
  }},
  "meta": {{
    "schema_version": "3.1",
    "generator": "llm_generated",
    "data_source": "generate_chart_llm",
    "record_count": 2,
    "marker_count": 2
  }}
}}
```

# 最佳实践
1. 确保经纬度字段存在且有效（中国境内：lng 73-135, lat 18-54）
2. 地图中心合理（取所有点的中心）
3. 缩放级别适中（避免过大或过小）
4. 标记点name必填
5. 可选字段按需添加（value/pollutant/industry/distance）

请直接返回JSON（不要markdown代码块）。
        """.strip()

        return prompt

    def get_examples(self) -> str:
        """获取地图示例"""
        return """
### 实际案例示例

**案例1**: 区域监测站点分布
- 输入数据: 10个监测站点的经纬度和实时浓度
- 生成结果: 地图展示站点位置，标注PM2.5浓度
- 特点: 清晰展示空间分布，识别高值区

**案例2**: 上风向企业分布
- 输入数据: 周边企业的位置、行业类型、距离
- 生成结果: 地图展示企业位置，标注行业和距离
- 特点: 识别潜在污染源空间分布
        """.strip()
