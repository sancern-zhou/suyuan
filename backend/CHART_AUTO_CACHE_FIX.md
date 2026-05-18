# 图表自动缓存功能说明

## 问题描述

之前生成的图表在前端显示为本地文件路径（`file:///home/xckj/...`），而不是可访问的URL（`/api/image/{image_id}`）。

**原因**：系统没有从Python代码输出中提取到图表路径，因此没有触发ImageCache缓存。

## 解决方案

系统采用了**双重保护机制**，确保图表能够自动缓存并生成可访问的URL：

### 1. 智能路径提取（方案1）✨

**功能**：系统会智能识别多种图表保存输出格式

**支持的输出格式**：
- 标准格式：`CHART_SAVED:/path/to/chart.png`
- 中文格式1：`图表已保存: /path/to/chart.png`
- 中文格式2：`图表已保存到: /path/to/chart.png`
- 中文格式3：`保存成功: /path/to/chart.png`
- 中文格式4：`保存图表到 /path/to/chart.png`

**实现位置**：`execute_python_tool.py:_extract_chart_paths()`

### 2. save_chart辅助函数（方案2）

**功能**：系统自动注入`save_chart()`辅助函数，方便用户保存图表并触发缓存

**使用示例**：
```python
import matplotlib.pyplot as plt
import numpy as np

# 创建图表
fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
ax.set_title('示例图表')

# ✅ 推荐：使用save_chart辅助函数
save_chart(fig, 'example.png', dpi=150)

# ✅ 也支持：直接使用plt.savefig
plt.savefig('chart2.png', dpi=150)
print('图表已保存: chart2.png')  # 系统会智能识别
```

### 3. 自动缓存流程

```
Python代码保存图表
    ↓
输出包含图表路径（任意格式）
    ↓
系统智能提取路径
    ↓
调用ImageCache.save()缓存图表
    ↓
生成 /api/image/{image_id} URL
    ↓
前端通过URL访问图表
```

## 使用方式

### 方式1：使用save_chart辅助函数（推荐）

```python
import matplotlib.pyplot as plt
import numpy as np

# 创建图表
fig, ax = plt.subplots()
x = np.linspace(0, 10, 100)
ax.plot(x, np.sin(x))
ax.set_xlabel('X轴')
ax.set_ylabel('Y轴')
ax.set_title('示例图表')

# 使用辅助函数保存（自动触发缓存）
save_chart(fig, 'my_chart.png', dpi=150)
plt.close()
```

**优势**：
- 简洁直观，只需一行代码
- 自动触发ImageCache缓存
- 自动生成可访问的URL

### 方式2：直接使用plt.savefig（智能识别）

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
ax.set_title('示例图表')

# 直接保存
plt.savefig('chart.png', dpi=150)

# ✅ 关键：打印图表路径（任意中文格式均可）
print('图表已保存到: chart.png')
# 或者
print(f'保存成功: chart.png')

plt.close()
```

**支持的输出格式**：
```python
# 所有这些格式都会被识别：
print('图表已保存: chart.png')
print('图表已保存到: chart.png')
print('保存成功: chart.png')
print('保存图表到: chart.png')
print('CHART_SAVED:chart.png')  # 标准格式
```

## 前端访问

图表缓存后，可以通过以下URL访问：

```
/api/image/{image_id}
```

**返回数据格式**：
```json
{
  "image_id": "matplotlib_xxx",
  "url": "/api/image/matplotlib_xxx",
  "local_path": "/home/xckj/.../chart.png"
}
```

## 验证方法

运行测试脚本验证功能：

```bash
cd backend
python test_chart_cache.py
```

**检查项**：
1. 图表是否成功保存到 `backend_data_registry/images/`
2. 系统日志中是否包含 `chart_cached` 或 `image_url`
3. 返回的result中是否包含 `visuals` 字段
4. `visuals[0].data.url` 是否为 `/api/image/{image_id}` 格式

## 技术实现

### 1. 路径提取逻辑

**文件**：`execute_python_tool.py:_extract_chart_paths()`

```python
def _extract_chart_paths(self, output: str) -> dict:
    """从Python代码输出中提取图表路径"""
    result = {"paths": [], "base64_data": []}

    # 支持的输出格式
    patterns = [
        r'图表已保存[:：]\s*(.+?\.(?:png|jpg|jpeg))',
        r'保存成功[:：]\s*(.+?\.(?:png|jpg|jpeg))',
        r'CHART_SAVED[:：](.+?\.(?:png|jpg|jpeg))',
        # ... 更多格式
    ]

    # 匹配并提取路径
    for line in output.split('\n'):
        for pattern in patterns:
            matches = re.findall(pattern, line)
            result["paths"].extend(matches)

    return result
```

### 2. 辅助函数注入

**文件**：`execute_python_tool.py:_inject_chinese_font_support()`

```python
# 在代码开头注入辅助函数
helper_code = """
def save_chart(fig, filename, dpi=150, bbox_inches='tight', facecolor='white'):
    '''保存图表并触发前端缓存'''
    filepath = os.path.join(charts_dir, filename)
    fig.savefig(filepath, dpi=dpi, bbox_inches=bbox_inches, facecolor=facecolor)

    # ✅ 关键：打印标准格式标记
    print(f'CHART_SAVED:{filepath}')

    return filepath
"""
```

### 3. 自动缓存触发

**文件**：`execute_python_tool.py:execute()`

```python
# 提取图表路径
chart_data = self._extract_chart_paths(result["data"].get("output", ""))

# 如果检测到图表，自动缓存到ImageCache
if chart_data.get("paths"):
    from app.services.image_cache import ImageCache
    image_cache = ImageCache()

    for chart_path in chart_data.get("paths"):
        # 读取图表文件
        with open(chart_path, 'rb') as f:
            base64_data = base64.b64encode(f.read()).decode('utf-8')

        # 缓存到ImageCache
        image_info = image_cache.save(base64_data=base64_data, chart_id=chart_id)

        # 添加到visuals字段
        result.setdefault("visuals", []).append({
            "id": chart_id,
            "type": "image",
            "title": "图表",
            "data": {
                "url": image_info["url"],
                "image_id": image_info["image_id"]
            }
        })
```

## 常见问题

### Q1：为什么我的图表没有生成URL？

**A**：检查是否输出了图表路径。确保代码中包含以下任一输出：
- `print('图表已保存: xxx.png')`
- `save_chart(fig, 'xxx.png')`
- `plt.savefig('xxx.png')` + 输出路径

### Q2：save_chart辅助函数在哪里？

**A**：系统会自动注入，无需手动导入。直接在代码中使用即可。

### Q3：支持中文文件名吗？

**A**：完全支持！例如：`save_chart(fig, '测试图表.png')`

### Q4：如何返回多个图表？

**A**：保存多个图表，每个图表都输出路径即可：
```python
save_chart(fig1, 'chart1.png')
save_chart(fig2, 'chart2.png')
save_chart(fig3, 'chart3.png')
# 所有图表都会被缓存并添加到visuals字段
```

## 相关文件

- `backend/app/tools/utility/execute_python_tool.py`：核心实现
- `backend/app/services/image_cache.py`：ImageCache服务
- `backend/test_chart_cache.py`：测试脚本
- `backend/CHART_AUTO_CACHE_FIX.md`：本文档

## 更新日志

- **2026-05-08**：初始版本，支持智能路径提取和save_chart辅助函数
