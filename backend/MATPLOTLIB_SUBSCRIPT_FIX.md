# matplotlib下标显示问题解决方案

## 问题描述

在使用matplotlib生成图表时，会遇到两个问题：

1. **Unicode下标字符显示异常**：中文字体（如方正小标宋简）不支持Unicode下标字符（如₂₅³μ），导致这些字符显示为方块或乱码
2. **LaTeX与中文混合问题**：matplotlib的mathtext引擎（用于渲染LaTeX数学符号）不支持中文字符，当代码中混合使用LaTeX和中文时，整个字符串会被mathtext渲染，导致中文显示为方块

## 解决方案

系统采用**简写格式策略**，自动将Unicode下标字符转换为简写格式：

### 1. 自动转换（推荐）✨

**execute_python_tool已内置自动转换功能**，会在代码执行前自动将Unicode下标转换为简写格式：

```python
# 你写的代码（包含Unicode下标）
ax.set_ylabel('PM₂.₅浓度 (μg/m³)')

# 系统自动转换为简写格式
ax.set_ylabel('PM2.5浓度 (ug/m3)')
```

**支持的自动转换**：
- ✅ PM₂.₅ → PM2.5
- ✅ μg/m³ → ug/m3
- ✅ O₃, NO₂, SO₂, CO₂ → O3, NO2, SO2, CO2
- ✅ m², m³ → m2, m3
- ✅ CH₄, N₂O → CH4, N2O

**核心优势**：
- 无需手动操作，直接写Unicode字符即可
- 避免LaTeX与中文混合导致的显示问题
- 适合日常使用场景

### 2. 为什么不使用LaTeX格式？

**问题场景**：
```python
# ❌ 错误：混合LaTeX和中文
ax.set_ylabel(r'PM$_{2.5}$浓度')  # "浓度"会显示为方块

# ❌ 问题原因：
# matplotlib检测到LaTeX格式（$...$），会使用mathtext引擎渲染整个字符串
# mathtext使用STIXGeneral字体，不支持中文字符
# 导致中文部分显示为方块
```

**解决方案**：
```python
# ✅ 正确：使用简写格式
ax.set_ylabel('PM2.5浓度')  # 中文正常显示

# ✅ 或者：将中文和LaTeX分离（需要复杂的字符串拼接）
ax.set_ylabel('浓度 ' + r'($\mu$g/m$^3$)')  # 不推荐，过于复杂
```

### 3. 何时使用LaTeX格式？

**适用场景**：纯英文的科学出版物，不需要中文字符

```python
# ✅ 可以使用LaTeX的场景（纯英文）
ax.set_ylabel(r'Concentration ($\mu$g/m$^3$)')  # 纯英文，正常显示
```

**不适用场景**：包含中文的标签
```python
# ❌ 不能使用LaTeX的场景（包含中文）
ax.set_ylabel(r'浓度 ($\mu$g/m$^3$)')  # 中文显示为方块
```

### 常见符号对照表

| Unicode字符 | 简写格式（推荐） | LaTeX格式（仅纯英文） |
|------------|----------------|-------------------|
| PM₂.₅ | `'PM2.5'` | `r'PM$_{2.5}$'` |
| μg/m³ | `'ug/m3'` | `r'$\mu$g/m$^3$'` |
| O₃ | `'O3'` | `r'O$_3$'` |
| NO₂ | `'NO2'` | `r'NO$_2$'` |
| SO₂ | `'SO2'` | `r'SO$_2$'` |
| CO₂ | `'CO2'` | `r'CO$_2$'` |
| m³ | `'m3'` | `r'm$^3$'` |
| m² | `'m2'` | `r'm$^2$'` |

### 完整代码示例

```python
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# 读取数据
df = pd.read_json('artifacts/task_1_city_daily.json')

# 创建图表
fig, ax = plt.subplots(figsize=(10, 6))

# 绘制柱状图
cities = df['城市']
pm25 = df['PM2.5']
ax.bar(cities, pm25, color='steelblue')

# 设置标签（使用简写格式）
ax.set_ylabel('PM2.5浓度 (ug/m3)', fontsize=11)
ax.set_xlabel('城市', fontsize=11)
ax.set_title('各城市PM2.5浓度对比', fontsize=12)

plt.xticks(rotation=45, ha='right')
plt.tight_layout()

# 保存图表（使用本地相对路径）
chart_path = 'backend_data_registry/reports/{report_id}/assets/images/chart_pm25_comparison.png'
plt.savefig(chart_path, dpi=150, bbox_inches='tight')
plt.close()

print(f"图表已保存：assets/images/chart_pm25_comparison.png")
```

### 两种格式选择

1. **简写格式**（日常使用推荐）⭐
   - 优点：简单直观，不依赖LaTeX，与中文完美兼容
   - 缺点：不符合严格的科学符号规范
   - 适用：一般报表和日常使用
   - **系统自动转换采用此格式**

2. **LaTeX格式**（科学出版物推荐）
   - 优点：符合科学符号规范，显示美观
   - 缺点：不能与中文混合使用
   - 适用：纯英文的科学论文
   - **需要手动使用，仅在纯英文场景下使用**

## 测试验证

系统已包含多个测试脚本，可以验证下标显示是否正常：

```bash
cd backend

# 测试1：LaTeX格式手动测试
python test_matplotlib_subscript.py

# 测试2：自动转换功能测试
python test_simple_conversion.py
```

测试会生成图表：
- `test_subscript_result.png`：LaTeX格式下标测试
- `test_simple_format.png`：简写格式测试
- `test_auto_converted.png`：自动转换功能测试

## 实现原理

### 自动转换机制

系统在`execute_python_tool.py`中实现了`_convert_unicode_subscript_to_latex()`方法：

1. **正则表达式匹配**：识别代码中的所有字符串字面量
2. **模式替换**：使用预定义的替换规则转换常见模式
3. **简写优先**：使用简写格式，避免LaTeX与中文混合问题

### 转换规则

```python
replacements = [
    # μ符号 → u
    (r'μ', r'u'),

    # PM2.5（特殊处理：小数形式）
    (r'PM₂\.?₅', r'PM2.5'),

    # 化学式下标（单个数字） - 简写格式
    (r'O₃', r'O3'),
    (r'NO₂', r'NO2'),
    (r'SO₂', r'SO2'),
    (r'CO₂', r'CO2'),
    (r'CH₄', r'CH4'),

    # 单位上标 - 简写格式
    (r'm³', r'm3'),
    (r'm²', r'm2'),
    (r'μg', r'ug'),

    # 其他
    (r'/m³', r'/m3'),
    (r'/m²', r'/m2'),
]
```

### 日志记录

转换过程会记录到日志中：

```
[info] unicode_subscript_converted strings_converted=4
```

## 相关文件

- `backend/app/tools/utility/execute_python_tool.py`：自动转换实现
- `backend/docs/skills/昨日污染特征与溯源分析.md`：技能文档中的使用规范
- `backend/test_matplotlib_subscript.py`：LaTeX格式测试脚本
- `backend/test_simple_conversion.py`：自动转换功能测试
- `backend/MATPLOTLIB_SUBSCRIPT_FIX.md`：本文档

## 注意事项

1. **Unicode字符自动转换**：系统会自动将Unicode下标转换为简写格式，无需手动处理
2. **避免LaTeX与中文混合**：如果需要手动使用LaTeX格式，确保不与中文混合
3. **简写格式优先**：在日常使用中，推荐使用简写格式（PM2.5、ug/m3等）
4. **纯英文场景**：只有在纯英文的科学出版物中，才建议使用LaTeX格式

## 常见问题

### Q1：为什么我的图表中文显示为方块？

**A**：可能是因为使用了LaTeX格式与中文混合。检查代码中是否有类似 `r'PM$_{2.5}$浓度'` 的字符串。解决方案：使用简写格式 `'PM2.5浓度'`。

### Q2：我需要严格科学符号怎么办？

**A**：如果需要严格科学符号，确保标签为纯英文，不包含中文字符。例如：`r'Concentration ($\mu$g/m$^3$)'`。

### Q3：系统会自动处理吗？

**A**：是的，系统会自动将常见的Unicode下标字符转换为简写格式。你只需要正常写Unicode字符（如'PM₂.₅'），系统会自动转换为'PM2.5'。
