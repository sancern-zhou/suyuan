"""
WindRosePrompt - 风向玫瑰图专用提示词
"""

from typing import Dict, Any, Optional
from .base import BaseChartPrompt


class WindRosePrompt(BaseChartPrompt):
    """
    风向玫瑰图专用Prompt

    适用场景：展示风向风速分布
    """

    @property
    def chart_type(self) -> str:
        return "wind_rose"

    def build_prompt(
        self,
        data: Dict[str, Any],
        title: Optional[str],
        **kwargs
    ) -> str:
        data_sample = self.format_data_sample(data, max_length=2500)

        prompt = f"""
{self.get_base_context()}

# 任务：生成风向玫瑰图（Wind Rose Chart）

## 数据样本
```json
{data_sample}
```

## 需求
- 标题: {title or '风向玫瑰图'}

## 风向玫瑰图特定规范

### 数据结构要求
风向玫瑰图的data字段必须包含：
```json
{{
  "sectors": [
    {{
      "direction": "N",        // 方位（N/NE/E/SE/S/SW/W/NW）
      "angle": 0,              // 角度（0-360）
      "avg_speed": 3.5,        // 平均风速（m/s）
      "max_speed": 8.2,        // 最大风速（m/s）
      "count": 120,            // 该方向的样本数
      "frequency": 0.15,       // 频率（占比）
      "speed_distribution": {{  // 风速分布
        "0-2": 30,
        "2-5": 60,
        "5-10": 25,
        "10+": 5
      }}
    }},
    ...  // 8个方向
  ],
  "legend": {{
    "N": "北风",
    "NE": "东北风",
    ...
  }},
  "statistics": {{
    "total_samples": 800,
    "avg_speed_overall": 4.2,
    "max_speed_overall": 12.5,
    "dominant_direction": "SE"
  }}
}}
```

### 数据处理流程
1. **识别风向字段**: 从原始数据中找到 wind_direction 或 direction 字段
2. **识别风速字段**: 从原始数据中找到 wind_speed 或 speed 字段
3. **方向分组**: 将风向角度分组到8个方位（N/NE/E/SE/S/SW/W/NW）
   - N: 337.5-22.5°
   - NE: 22.5-67.5°
   - E: 67.5-112.5°
   - SE: 112.5-157.5°
   - S: 157.5-202.5°
   - SW: 202.5-247.5°
   - W: 247.5-292.5°
   - NW: 292.5-337.5°
4. **统计计算**: 计算每个方向的平均风速、频率、风速分布
5. **排序**: 按角度从0到315排列（N, NE, E, SE, S, SW, W, NW）

### 风速等级分组
- 0-2 m/s: 微风
- 2-5 m/s: 轻风
- 5-10 m/s: 和风
- 10+ m/s: 强风

{self.get_examples()}

### 输出示例（完整）
```json
{{
  "id": "wind_rose_2025",
  "type": "wind_rose",
  "title": "{title or '风向玫瑰图'}",
  "data": {{
    "sectors": [
      {{"direction": "N", "angle": 0, "avg_speed": 3.5, "max_speed": 8.2, "count": 120, "frequency": 0.15, "speed_distribution": {{"0-2": 30, "2-5": 60, "5-10": 25, "10+": 5}}}},
      {{"direction": "NE", "angle": 45, "avg_speed": 4.2, "max_speed": 9.5, "count": 100, "frequency": 0.125, "speed_distribution": {{"0-2": 20, "2-5": 50, "5-10": 25, "10+": 5}}}},
      {{"direction": "E", "angle": 90, "avg_speed": 3.8, "max_speed": 7.8, "count": 95, "frequency": 0.12, "speed_distribution": {{"0-2": 25, "2-5": 55, "5-10": 15, "10+": 0}}}},
      {{"direction": "SE", "angle": 135, "avg_speed": 5.2, "max_speed": 12.5, "count": 150, "frequency": 0.19, "speed_distribution": {{"0-2": 10, "2-5": 60, "5-10": 60, "10+": 20}}}},
      {{"direction": "S", "angle": 180, "avg_speed": 4.5, "max_speed": 10.2, "count": 110, "frequency": 0.14, "speed_distribution": {{"0-2": 20, "2-5": 50, "5-10": 35, "10+": 5}}}},
      {{"direction": "SW", "angle": 225, "avg_speed": 3.2, "max_speed": 6.5, "count": 80, "frequency": 0.10, "speed_distribution": {{"0-2": 35, "2-5": 40, "5-10": 5, "10+": 0}}}},
      {{"direction": "W", "angle": 270, "avg_speed": 2.8, "max_speed": 5.8, "count": 75, "frequency": 0.09, "speed_distribution": {{"0-2": 40, "2-5": 30, "5-10": 5, "10+": 0}}}},
      {{"direction": "NW", "angle": 315, "avg_speed": 3.0, "max_speed": 7.2, "count": 70, "frequency": 0.09, "speed_distribution": {{"0-2": 30, "2-5": 35, "5-10": 5, "10+": 0}}}}
    ],
    "legend": {{
      "N": "北风", "NE": "东北风", "E": "东风", "SE": "东南风",
      "S": "南风", "SW": "西南风", "W": "西风", "NW": "西北风"
    }},
    "statistics": {{
      "total_samples": 800,
      "avg_speed_overall": 3.9,
      "max_speed_overall": 12.5,
      "dominant_direction": "SE"
    }}
  }},
  "meta": {{
    "schema_version": "3.1",
    "unit": "m/s",
    "generator": "llm_generated",
    "data_source": "generate_chart_llm",
    "record_count": 800
  }}
}}
```

# 最佳实践
1. 确保wind_direction和wind_speed字段存在
2. 正确分组风向到8个方位
3. 计算风速分布（4个等级）
4. 识别主导风向（频率最高）
5. 单位统一为m/s

请直接返回JSON（不要markdown代码块）。
        """.strip()

        return prompt

    def get_examples(self) -> str:
        """获取风向玫瑰图示例"""
        return """
### 实际案例示例

**案例1**: 深圳市2025年11月风场特征
- 输入数据: 800条气象记录，包含wind_speed和wind_direction字段
- 主导风向: 东南风（SE），频率19%
- 平均风速: 3.9 m/s
- 生成结果: 8方位风向玫瑰图，清晰展示风向分布和风速等级

**案例2**: 污染事件期间风场分析
- 输入数据: 污染事件期间48小时的风速风向数据
- 特征: 风速较小（平均2.1 m/s），风向多变
- 生成结果: 突出低风速区间，标注静风频率
        """.strip()
