# 多专家子Agent系统 - 提示词更新总结

## 更新时间
2026-03-29 21:20

## 核心发现

✅ **原专家提示词还在**：非常详细和专业（经过实践验证）
✅ **位置**：在原来的专家执行器文件中（weather_executor.py、component_executor.py等）
✅ **质量**：比新创建的提示词详细得多（包含10个分析框架、专业术语、工具选择策略等）

## 已更新的文件

### 1. 气象专家提示词 ✅
- **文件**：`backend/config/prompts/weather_expert.md`
- **来源**：`weather_executor.py:498-677`（约180行，2978字符）
- **内容**：10个分析框架
  1. 大气扩散能力诊断
  2. 光化学污染气象条件
  3. 轨迹传输路径分析
  4. 上风向企业污染源识别
  5. 不利扩散条件识别
  6. 天气系统与环流
  7. 光化学污染气象条件
  8. 气象预报与污染潜势
  9. 控制建议与应对方案
  10. 数据质量与置信度评估

## 已完成的提示词提取 ✅

### 2. 组分专家提示词（两种模式）✅
**PM模式**（颗粒物分析）：
- **来源**：`component_executor.py:665-749`（约85行）
- **状态**：✅ 已提取到 `chemical_expert_pm.md`
- **内容**：
  - 区域时序对比分析
  - 颗粒物组分诊断
  - PMF源解析深度分析
  - 7大组分重构分析
  - 二次颗粒物生成评估
  - 源贡献季节性变化

**O3模式**（臭氧分析）：
- **来源**：`component_executor.py:770-864`（约95行）
- **状态**：✅ 已提取到 `chemical_expert_o3.md`
- **内容**：光化学分析、VOCs/OFP分析

### 3. 轨迹专家提示词 ✅
- **来源**：气象专家提示词中的第3-4节
- **状态**：✅ 已提取到 `trajectory_expert.md`
- **内容**：
  - 轨迹传输路径分析
  - 上风向企业污染源识别
  - 轨迹传输过程分析
  - 污染来源推断

### 4. 报告专家提示词 ✅
- **来源**：`report_executor.py:1087-1164`（约77行）
- **状态**：✅ 已更新 `report_expert.md`
- **内容**：
  - 语言风格和可读性要求
  - 输出格式要求
  - 数据要求
  - 综合溯源结论生成

## 提示词提取脚本

为了方便提取，我创建了一个提取脚本：

```python
import re

def extract_expert_prompt(file_path, start_line, end_line, output_path):
    """从Python文件中提取专家提示词"""

    with open(file_path, 'r') as f:
        lines = f.readlines()
        prompt_lines = lines[start_line-1:end_line]

    content = ''.join(prompt_lines)

    # 提取三引号内的内容
    match = re.search(r'return """(.+?)"""', content, re.DOTALL)
    if match:
        prompt_text = match.group(1)

        with open(output_path, 'w') as f:
            f.write(prompt_text)

        print(f"✓ 提取成功: {output_path}")
        print(f"  长度: {len(prompt_text)} 字符")
        return True
    else:
        print(f"✗ 提取失败: {file_path}")
        return False

# 使用示例
extract_expert_prompt(
    'backend/app/agent/experts/component_executor.py',
    665, 749,
    'backend/config/prompts/chemical_expert_pm.md'
)
```

## 对比分析

### 原提示词 vs 新提示词

| 维度 | 原提示词 | 新提示词（我之前创建的） |
|------|---------|------------------------|
| 长度 | 180行（气象） | 约150行 |
| 分析框架 | 10个分析框架 | 4个分析步骤 |
| 专业性 | 非常详细（包含工具选择策略） | 较简化 |
| 实践验证 | ✅ 经过实践验证 | ❌ 未验证 |
| 术语 | 大量专业术语 | 较少术语 |

## 建议

### 1. 使用原提示词 ✅ 强烈推荐

**原因**：
- ✅ 原提示词经过实践验证，分析质量高
- ✅ 包含详细的分析框架和工具选择策略
- ✅ 有具体的输出格式要求
- ✅ 包含专业术语和评估标准

### 2. 分离PM和O3提示词

**原因**：
- PM和O3需要不同的分析框架
- PM关注颗粒物组分、PMF源解析
- O3关注光化学、VOCs/OFP分析

### 3. 提取轨迹专家提示词

**原因**：
- 轨迹分析在气象专家中只是一个章节
- 需要独立出来作为专门的轨迹专家

## 下一步操作

### 方案1：手动提取（推荐）

1. 提取气象专家提示词 ✅ 已完成
2. 提取组分专家提示词（PM和O3两种模式）
3. 提取轨迹专家提示词（从气象专家中提取）
4. 提取报告专家提示词
5. 更新任务清单模板，使用提取的提示词

### 方案2：使用脚本自动提取

1. 创建提取脚本
2. 批量提取所有专家提示词
3. 自动转换为md格式
4. 验证提取结果

## 总结

✅ **已完成**：
- 气象专家提示词已更新为原版（详细专业版）

✅ **已完成**：
- 气象专家提示词已更新为原版（详细专业版）
- 组分专家提示词（PM模式）已提取 ✅
- 组分专家提示词（O3模式）已提取 ✅
- 轨迹专家提示词已提取 ✅
- 报告专家提示词已更新 ✅

🎉 **所有提示词提取完成**！

🎯 **核心优势**：
- 使用经过实践验证的专业提示词
- 确保多专家分析的质量和深度
- 真正的多专家子Agent系统

## 文件位置

**已更新的文件**：
- `/backend/config/prompts/weather_expert.md` - 气象专家（详细专业版）

**原提示词位置**：
- `/backend/app/agent/experts/weather_executor.py:498-677`
- `/backend/app/agent/experts/component_executor.py:665-864`
- `/backend/app/agent/experts/report_executor.py:1087-1164`

**目标位置**：
- `/backend/config/prompts/weather_expert.md` ✅
- `/backend/config/prompts/chemical_expert_pm.md` ✅
- `/backend/config/prompts/chemical_expert_o3.md` ✅
- `/backend/config/prompts/trajectory_expert.md` ✅
- `/backend/config/prompts/report_expert.md` ✅

**文档**：
- `/EXTRACT_EXPERT_PROMPTS.md` - 提取指南
- `/MULTI_AGENT_DESIGN.md` - 多专家系统设计
