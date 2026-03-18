"""
PiePrompt - 饼图专用提示词
"""

from typing import Dict, Any, Optional
from .base import BaseChartPrompt


class PiePrompt(BaseChartPrompt):
    """
    饼图专用Prompt

    适用场景：展示占比/组成关系
    """

    @property
    def chart_type(self) -> str:
        return "pie"

    def build_prompt(
        self,
        data: Dict[str, Any],
        title: Optional[str],
        **kwargs
    ) -> str:
        data_sample = self.format_data_sample(data, max_length=2000)

        prompt = f"""
{self.get_base_context()}

# 任务：生成饼图（Pie Chart）

## 数据样本
```json
{data_sample}
```

## 需求
- 标题: {title or '饼图'}

## 饼图特定规范

### 数据结构要求
饼图的data字段必须是数组，每个元素包含：
```json
[
  {{"name": "类别名称", "value": 数值}},
  {{"name": "类别2", "value": 数值2}},
  ...
]
```

### 数据处理规则
1. **识别分类字段**: 从数据中找到表示类别的字段（name/category/type等）
2. **识别数值字段**: 从数据中找到表示数值的字段（value/count/amount等）
3. **计算占比**: 系统会自动计算百分比，无需手动计算
4. **排序**: 建议按value降序排列，突出主要类别
5. **限制数量**: 如果类别过多（>10），只保留TOP 10，其他归为"其他"

### 常见数据格式转换

**格式1: 对象格式**
输入: `{{"VOCs": 45.2, "PM2.5": 32.1, "NOx": 22.7}}`
输出:
```json
[
  {{"name": "VOCs", "value": 45.2}},
  {{"name": "PM2.5", "value": 32.1}},
  {{"name": "NOx", "value": 22.7}}
]
```

**格式2: 嵌套列表**
输入: `[{{"污染物": "VOCs", "浓度": 45.2}}, ...]`
输出:
```json
[
  {{"name": "VOCs", "value": 45.2}},
  ...
]
```

{self.get_examples()}

### 输出示例（完整）
```json
{{
  "id": "pie_2025",
  "type": "pie",
  "title": "{title or '饼图'}",
  "data": [
    {{"name": "VOCs", "value": 45.2}},
    {{"name": "PM2.5", "value": 32.1}},
    {{"name": "NOx", "value": 22.7}}
  ],
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
1. 确保name字段是字符串类型
2. 确保value字段是数值类型（number，不是string）
3. 移除value为0或null的项
4. 如果有单位信息，添加到meta.unit

请直接返回JSON（不要markdown代码块）。
        """.strip()

        return prompt

    def get_examples(self) -> str:
        """获取饼图示例"""
        return """
### 实际案例示例

**案例1**: 污染源贡献率分析
- 输入数据: PMF源解析结果，6个污染源
- 生成结果: 饼图清晰展示各源贡献占比
- 特点: 按贡献率降序排列，便于识别主要污染源

**案例2**: VOCs物种组成
- 输入数据: 100多种VOCs物种浓度
- 处理: 只保留TOP 10，其他归为"其他"
- 生成结果: 简洁饼图，突出主要物种
        """.strip()
