# ECharts图表HTML报告支持

## 修改内容

为溯源报告生成工具添加了HTML报告中动态渲染ECharts图表的功能。

### 1. 数据结构修改

**文件**: `backend/app/tools/reporting/generate_tracing_report/tool.py`

在`_render_echarts_to_png`方法的返回值中添加了`chart_data`字段：

```python
return {
    "id": visual.get("id", f"echarts_{config_hash}"),
    "type": "echarts",
    "title": visual.get("title", "未命名图表"),
    "image_path": str(dest_path),
    "relative_path": f"assets/images/{filename}",
    "expert": expert,
    # 新增：保留原始v3.1数据用于HTML报告渲染
    "chart_data": {
        "type": chart_type,
        "data": chart_data,
        "title": title,
        "meta": meta
    }
}
```

### 2. 新增函数

#### `_generate_echarts_html_block`

生成交互式ECharts图表的HTML代码块：

```python
def _generate_echarts_html_block(
    self,
    visual_id: str,
    chart_data: Dict[str, Any]
) -> str:
    """
    Generate a self-contained HTML block for interactive ECharts embedding.

    支持的图表类型：
    - pie: 饼图
    - bar: 柱状图
    - line: 折线图
    - timeseries: 时序图
    """
```

**特性**：
- 自动加载ECharts库（CDN）
- 响应式设计（监听window resize）
- 支持v3.1格式数据自动转换为ECharts配置
- 独立作用域（IIFE），避免全局变量冲突

#### `_insert_echarts_charts`

在报告中插入ECharts图表：

```python
def _insert_echarts_charts(
    self,
    content: str,
    visuals_by_expert: Dict[str, List[Dict[str, Any]]]
) -> str:
    """
    将ECharts图表插入到综合分析章节

    插入位置：报告末尾（元数据之前）
    """
```

### 3. 修改函数

#### `_generate_simplified_analysis`

在生成综合分析章节时，调用`_insert_echarts_charts`：

```python
# 插入ECharts图表
try:
    content = self._insert_echarts_charts(
        content,
        visuals_by_expert
    )
except Exception as e:
    logger.warning("failed_to_insert_echarts_charts", error=str(e))
```

## 渲染逻辑

### HTML报告（动态渲染）

使用Quarto的条件内容语法：

```markdown
::: {.content-hidden when-format="docx"}

```{=html}
<div id="echarts_container_xxx" style="width:100%;height:500px;"></div>
<script>
(function() {
    // ECharts配置和渲染逻辑
})();
</script>
```

:::

::: {.content-hidden when-format="html"}

![图表](assets/images/xxx.png)

:::
```

### Word/PPT报告（静态图片）

```markdown
![图表标题](assets/images/xxx.png)
```

## 支持的图表类型

| 图表类型 | v3.1数据格式 | HTML渲染 | Word/PPT |
|---------|-------------|----------|----------|
| pie | `[{name, value}, ...]` | ✅ 交互式饼图 | ✅ PNG |
| bar | `{x: [], y: []}` | ✅ 交互式柱状图 | ✅ PNG |
| line | `{x: [], y: []}` | ✅ 交互式折线图 | ✅ PNG |
| timeseries | `{x: [], series: [...]}` | ✅ 交互式时序图 | ✅ PNG |

## 报告结构

```
## 综合分析

[分析文字内容]

[企业分布地图 - 插入在轨迹图之后]

---

## 图表分析  ← 新增章节

### 图表标题1
[HTML: 交互式ECharts | Word/PPT: 静态图片]

### 图表标题2
[HTML: 交互式ECharts | Word/PPT: 静态图片]

---

**报告生成时间**: ...
**分析精度**: ...
**参与专家**: ...
**状态**: ...
```

## 技术细节

### ECharts版本
- CDN: `https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js`
- 版本: 5.5.0

### 容器样式
```css
width: 100%;
height: 500px;
margin: 1em 0;
```

### 响应式支持
```javascript
window.addEventListener('resize', function() {
    myChart.resize();
});
```

### 懒加载机制
```javascript
function initChart() {
    if (typeof echarts === 'undefined') {
        setTimeout(initChart, 200);
        return;
    }
    // 初始化图表
}
```

## 依赖关系

```
v3.1图表数据
    ↓
ChartV3ToEChartsConverter (转换为ECharts配置)
    ↓
_generate_echarts_html_block (生成HTML代码)
    ↓
_insert_echarts_charts (插入到报告)
    ↓
HTML报告: 动态渲染
Word/PPT报告: 静态PNG
```

## 日期

2026-05-11
