"""
BarPrompt - 柱状图专用提示词
"""

from typing import Dict, Any, Optional
from .base import BaseChartPrompt


class BarPrompt(BaseChartPrompt):
    """
    柱状图专用Prompt

    适用场景：对比不同类别的数值
    """

    @property
    def chart_type(self) -> str:
        return "bar"

    def build_prompt(
        self,
        data: Dict[str, Any],
        title: Optional[str],
        **kwargs
    ) -> str:
        data_sample = self.format_data_sample(data, max_length=2000)

        prompt = f"""
{self.get_base_context()}

# 任务：生成柱状图（Bar Chart）

## 数据样本
```json
{data_sample}
```

## 需求
- 标题: {title or '柱状图'}

## 柱状图特定规范

### 数据结构要求
柱状图的data字段必须包含x和y数组：
```json
{{
  "x": ["类别1", "类别2", "类别3", ...],  // X轴标签（类别）
  "y": [数值1, 数值2, 数值3, ...]          // Y轴数值
}}
```

或支持多系列柱状图：
```json
{{
  "x": ["类别1", "类别2", "类别3"],
  "series": [
    {{"name": "系列1", "data": [10, 20, 30]}},
    {{"name": "系列2", "data": [15, 25, 35]}}
  ]
}}
```

### 数据处理规则
1. **识别X轴字段**: 类别/站点名/时间点等
2. **识别Y轴字段**: 数值/浓度/数量等
3. **排序建议**:
   - 按Y轴数值降序（突出高值）
   - 或按X轴自然顺序（时间序列）
4. **数值类型**: 确保Y轴是number类型，不是string

### 常见数据格式转换

**格式1: 列表格式**
输入: `[{{"station": "A站", "value": 45.2}}, {{"station": "B站", "value": 32.1}}, ...]`
输出:
```json
{{
  "x": ["A站", "B站"],
  "y": [45.2, 32.1]
}}
```

**格式2: 对象格式**
输入: `{{"A站": 45.2, "B站": 32.1}}`
输出:
```json
{{
  "x": ["A站", "B站"],
  "y": [45.2, 32.1]
}}
```

{self.get_examples()}

### 输出示例（完整）
```json
{{
  "id": "bar_2025",
  "type": "bar",
  "title": "{title or '柱状图'}",
  "data": {{
    "x": ["站点A", "站点B", "站点C"],
    "y": [45.2, 32.1, 28.5]
  }},
  "meta": {{
    "schema_version": "3.1",
    "unit": "μg/m³",
    "generator": "llm_generated",
    "data_source": "generate_chart_llm",
    "record_count": 3
  }}
}}
```

# 最佳实践
1. X轴标签简洁明了
2. Y轴数值必须是number类型
3. 如果类别过多（>20），考虑只展示TOP 20
4. 添加单位到meta.unit

请直接返回JSON（不要markdown代码块）。
        """.strip()

        return prompt

    def get_examples(self) -> str:
        """获取柱状图示例"""
        return """
### 实际案例示例

**案例1**: 多站点污染物浓度对比
- 输入数据: 5个监测站点的PM2.5浓度
- 生成结果: 柱状图按浓度降序排列
- 特点: 清晰展示站点间差异

**案例2**: 企业排放量对比
- 输入数据: 10家企业的VOCs排放量
- 处理: 按排放量降序
- 生成结果: 突出重点排放企业
        """.strip()
