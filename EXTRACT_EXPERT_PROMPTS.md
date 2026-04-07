# 从原专家执行器提取提示词指南

## 发现

原来的专家执行器文件还在，包含非常详细和专业的提示词：

### 文件位置
- `/backend/app/agent/experts/weather_executor.py` - 气象专家
- `/backend/app/agent/experts/component_executor.py` - 组分专家
- `/backend/app/agent/experts/viz_executor.py` - 可视化专家
- `/backend/app/agent/experts/report_executor.py` - 报告专家

### 提示词位置

#### 1. 气象专家提示词
**文件**：`weather_executor.py`
**方法**：`_get_summary_prompt()`
**行号**：第498-677行（约180行）
**核心内容**：
- 大气扩散能力诊断
- 光化学污染气象条件
- 轨迹传输路径分析
- 上风向企业污染源识别
- 不利扩散条件识别
- 天气系统与环流
- 气象预报与污染潜势
- 控制建议与应对方案
- 数据质量与置信度评估

#### 2. 组分专家提示词
**文件**：`component_executor.py`
**方法**：`_get_summary_prompt(analysis_type)`
**行号**：
- PM模式：第665-749行（约85行）
- O3模式：第770-864行（约95行）
- 通用模式：第874-950行（约77行）
**核心内容**：
- **PM模式**：颗粒物化学分析、PMF源解析、7大组分重构
- **O3模式**：光化学分析、VOCs/OFP分析
- **通用模式**：综合组分分析

#### 3. 可视化专家提示词
**文件**：`viz_executor.py`
**方法**：`_get_summary_prompt()`
**行号**：第117-131行（约15行）
**核心内容**：
- 图表类型评估
- 数据展示评估
- 补充图表建议

#### 4. 报告专家提示词
**文件**：`report_executor.py`
**方法**：`prompt_template`
**行号**：第1087-1164行（约77行）
**核心内容**：
- 综合专家分析结果
- 生成Markdown格式溯源报告
- 结论与建议章节生成

## 提取命令

### 气象专家提示词
```bash
sed -n '498,677p' /home/xckj/suyuan/backend/app/agent/experts/weather_executor.py > \
  /home/xckj/suyuan/backend/config/prompts/weather_expert.md
```

### 组分专家提示词（PM模式）
```bash
sed -n '665,749p' /home/xckj/suyuan/backend/app/agent/experts/component_executor.py > \
  /home/xckj/suyuan/backend/config/prompts/chemical_expert_pm.md
```

### 组分专家提示词（O3模式）
```bash
sed -n '770,864p' /home/xckj/suyuan/backend/app/agent/experts/component_executor.py > \
  /home/xckj/suyuan/backend/config/prompts/chemical_expert_o3.md
```

### 报告专家提示词
```bash
sed -n '1087,1164p' /home/xckj/suyuan/backend/app/agent/experts/report_executor.py > \
  /home/xckj/suyuan/backend/config/prompts/report_expert.md
```

## 提示词对比

### 原提示词 vs 新提示词

| 专家 | 原提示词特点 | 新提示词特点 | 建议 |
|------|--------------|--------------|------|
| 气象专家 | 非常详细（180行），包含10个分析框架 | 简化版（约150行），包含4个分析步骤 | **使用原提示词** |
| 组分专家 | 非常详细，分PM/O3/通用三种模式 | 简化版，通用模式 | **使用原提示词** |
| 轨迹专家 | 包含在气象专家提示词中 | 独立提示词 | **从气象专家中提取** |
| 报告专家 | 较详细（77行），包含格式要求 | 简化版（约180行） | **使用原提示词** |

## 建议

### 1. 使用原提示词 ✅ 推荐

**原因**：
- 原提示词经过实践验证，分析质量高
- 包含详细的分析框架和专业术语
- 有具体的输出格式要求

**操作**：
```bash
# 提取原提示词到md文件
sed -n '498,677p' /home/xckj/suyuan/backend/app/agent/experts/weather_executor.py > \
  /home/xckj/suyuan/backend/config/prompts/weather_expert.md

# 清理代码格式，转换为md格式
# （需要手动调整格式，去除Python代码语法）
```

### 2. 创建统一的提示词结构

**原提示词结构**（以气象专家为例）：
```python
return """你是资深大气环境气象分析专家，专注快速污染溯源场景。

【核心职责】
基于气象数据和轨迹分析，生成专业的污染溯源气象报告。
重点关注：
- 污染传输路径和上风向企业识别
...

【分析框架】
## 1. 大气扩散能力诊断
...
## 2. 光化学污染气象条件
...
...
"""
```

**转换为md格式**：
```markdown
# 气象分析专家提示词

你是资深大气环境气象分析专家，专注快速污染溯源场景。

## 核心职责
基于气象数据和轨迹分析，生成专业的污染溯源气象报告。

重点关注：
- 污染传输路径和上风向企业识别
- 大气扩散条件对污染形成的影响
...

## 分析框架

### 1. 大气扩散能力诊断
...
### 2. 光化学污染气象条件
...
```

### 3. 分离PM和O3提示词

**原因**：
- PM分析关注颗粒物组分、PMF源解析
- O3分析关注光化学、VOCs/OFP
- 两种污染物需要不同的分析框架

**操作**：
- 创建 `chemical_expert_pm.md`（颗粒物分析）
- 创建 `chemical_expert_o3.md`（臭氧分析）
- 在任务清单中根据污染物类型选择对应的提示词

### 4. 轨迹专家提示词

**发现**：
- 轨迹分析包含在气象专家提示词中（第3节）
- 需要独立出来

**操作**：
- 从气象专家提示词中提取轨迹相关部分
- 创建独立的 `trajectory_expert.md`

## 下一步操作

### 方案1：手动提取和转换（推荐）

1. **提取原提示词**：
```bash
# 气象专家
sed -n '498,677p' backend/app/agent/experts/weather_executor.py > /tmp/weather_raw.txt

# 组分专家（PM）
sed -n '665,749p' backend/app/agent/experts/component_executor.py > /tmp/component_pm_raw.txt

# 组分专家（O3）
sed -n '770,864p' backend/app/agent/experts/component_executor.py > /tmp/component_o3_raw.txt

# 报告专家
sed -n '1087,1164p' backend/app/agent/experts/report_executor.py > /tmp/report_raw.txt
```

2. **转换为md格式**：
   - 去除Python代码语法
   - 转换为Markdown格式
   - 添加章节标题
   - 保持原有内容

3. **保存到prompts目录**：
   - `prompts/weather_expert.md`
   - `prompts/chemical_expert_pm.md`
   - `prompts/chemical_expert_o3.md`
   - `prompts/trajectory_expert.md`
   - `prompts/report_expert.md`

### 方案2：使用脚本自动转换

创建一个Python脚本，自动提取和转换提示词：

```python
import re

def extract_prompt_from_python(file_path, start_line, end_line, output_path):
    """从Python文件中提取提示词并转换为md格式"""

    # 读取指定行范围
    with open(file_path, 'r') as f:
        lines = f.readlines()
        prompt_lines = lines[start_line-1:end_line]

    # 提取提示词内容
    prompt_text = ''.join(prompt_lines)

    # 提取三引号内的内容
    match = re.search(r'"""(.*)"""', prompt_text, re.DOTALL)
    if match:
        content = match.group(1)

        # 转换为md格式
        md_content = content.replace('【', '\n## ').replace('】', '\n')
        md_content = md_content.replace('**', '\n**')

        # 保存
        with open(output_path, 'w') as f:
            f.write(md_content)

        print(f"✓ 提取成功: {output_path}")
    else:
        print(f"✗ 提取失败: 未找到三引号包裹的提示词")

# 使用示例
extract_prompt_from_python(
    'backend/app/agent/experts/weather_executor.py',
    498, 677,
    'backend/config/prompts/weather_expert.md'
)
```

## 文件清单

### 需要提取的提示词

1. ✅ **气象专家提示词**（weather_executor.py:498-677）
2. ✅ **组分专家提示词-PM模式**（component_executor.py:665-749）
3. ✅ **组分专家提示词-O3模式**（component_executor.py:770-864）
4. ✅ **轨迹专家提示词**（从weather_executor.py中提取）
5. ✅ **报告专家提示词**（report_executor.py:1087-1164）

### 提取后的文件

1. `prompts/weather_expert.md` - 气象专家
2. `prompts/trajectory_expert.md` - 轨迹专家
3. `prompts/chemical_expert_pm.md` - 组分专家（PM模式）
4. `prompts/chemical_expert_o3.md` - 组分专家（O3模式）
5. `prompts/report_expert.md` - 报告专家

## 总结

✅ **原专家提示词还在**：非常详细和专业
✅ **需要提取和转换**：从Python代码转换为md文件
✅ **保持专业性**：使用原提示词的详细内容
✅ **增强灵活性**：独立的md文件易于调整
✅ **支持多模式**：PM和O3使用不同的提示词

建议使用原提示词，确保分析质量！
