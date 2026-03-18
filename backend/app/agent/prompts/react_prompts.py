"""
ReAct Agent Prompts

注意：系统提示词已由 expert_prompt.py / assistant_prompt.py 替代。
本文件仅保留 FINISH_SUMMARY 提示词及其格式化函数。
"""

# ========================================
# FINISH_SUMMARY 提示词
# ========================================

FINISH_SUMMARY_PROMPT = """# 任务
你是一个专业的大气环境专家。请根据以下信息，生成面向用户的最终回答。

## 用户原始需求
{user_query}

## 已获取的工具结果数据
{tool_results}

## 最终思考内容
{final_thought}

## 输出要求
请直接输出最终答案（Markdown格式），不需要 JSON 代码块：
1. 直接回答用户问题
2. 检查数据的完整性和合理性，绝对禁止编造数据，如数据无法满足要求，可以回复原因，无需编造。
3. 展示关键数据（从工具结果中提取）
4. 给出专业分析结论
5. **图片输出规范**：
   - ✅ **HTTP URL图片**：使用Markdown图片语法 `![描述](http://...)`
   - ❌ **本地路径**：直接输出纯文本路径，**禁止**使用Markdown图片语法（浏览器无法访问本地文件）
   - 示例：
     - 正确：`![分析图表](http://localhost:8000/api/image/chart_123)` （HTTP URL）
     - 正确：`图片已保存到：D:/溯源/backend_data_registry/temp_images/chart.png` （本地路径，纯文本）
     - 错误：`![图片](D:/溯源/backend_data_registry/temp_images/chart.png)` （本地路径，禁止Markdown）
```

记住：不要重复中间推理过程，直接输出面向用户的自然语言回答，结构清晰，内容完整。"""


# ========================================
# 格式化函数
# ========================================

def format_finish_summary_prompt(
    user_query: str,
    tool_results: str,
    final_thought: str
) -> str:
    """格式化 FINISH_SUMMARY 提示词"""
    result = FINISH_SUMMARY_PROMPT
    result = result.replace('{user_query}', user_query)
    result = result.replace('{tool_results}', tool_results)
    result = result.replace('{final_thought}', final_thought)
    return result
