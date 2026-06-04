# ECharts官方示例检索完整指南

## 检索环境

ECharts官方示例已下载到：`/tmp/echarts-examples-gh-pages/public/examples/ts/`

## 检索方法

### 1. 按图表类型检索

使用 `search_files` 工具按文件名模式检索：

```python
# 柱状图示例
search_files(
    pattern="bar-*.ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 散点图示例
search_files(
    pattern="scatter-*.ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 饼图示例
search_files(
    pattern="pie-*.ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 折线图示例
search_files(
    pattern="line-*.ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 仪表盘示例
search_files(
    pattern="gauge-*.ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)
```

### 2. 按元数据检索

使用 `grep` 工具在示例文件中搜索元数据标签：

```python
# 搜索仪表盘类
grep(
    pattern="category: gauge",
    type="ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 搜索简单示例（difficulty: 0 表示最简单）
grep(
    pattern="difficulty: 0",
    type="ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 搜索中等难度示例
grep(
    pattern="difficulty: 1",
    type="ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 搜索堆叠图
grep(
    pattern="stack",
    type="ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 搜索动态数据示例
grep(
    pattern="dynamic",
    type="ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)
```

### 3. 查看目录结构

使用 `list_directory` 浏览所有图表类型：

```python
list_directory(
    path="/tmp/echarts-examples-gh-pages/public/examples/ts",
    recursive=false
)
```

返回示例：
```
bar-simple.ts
bar-stack.ts
scatter-simple.ts
line-area.ts
pie-nest.ts
gauge-simple.ts
...
```

### 4. 读取具体示例

使用 `read_file` 读取示例内容：

```python
read_file(
    file_path="/tmp/echarts-examples-gh-pages/public/examples/ts/bar-simple.ts"
)
```

## 使用检索到的示例

### 步骤1：读取示例代码
```python
read_file(file_path=".../bar-simple.ts")
```

### 步骤2：提取 option 配置
示例文件中包含 `option` 对象，这是ECharts的核心配置：
```typescript
option = {
  xAxis: {...},
  yAxis: {...},
  series: [...]
}
```

### 步骤3：转换为Python格式
将TypeScript配置转换为Python字典：
```python
result = {
    "xAxis": {...},
    "yAxis": {...},
    "series": [...]
}
print(json.dumps(result, ensure_ascii=False))
```

## 常用示例路径

| 图表类型 | 文件路径 |
|---------|---------|
| 简单柱状图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/bar-simple.ts` |
| 堆叠柱状图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/bar-stack.ts` |
| 极坐标柱状图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/bar-polar.ts` |
| 简单折线图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/line-simple.ts` |
| 面积折线图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/line-area.ts` |
| 阶梯折线图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/line-step.ts` |
| 简单饼图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/pie-simple.ts` |
| 环形饼图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/pie-doughnut.ts` |
| 玫瑰饼图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/pie-rose-type.ts` |
| 嵌套饼图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/pie-nest.ts` |
| 简单散点图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/scatter-simple.ts` |
| 仪表盘 | `/tmp/echarts-examples-gh-pages/public/examples/ts/gauge-simple.ts` |
| 关系图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/graph-simple.ts` |
| 桑基图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/sankey-simple.ts` |
| 矩形树图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/treemap-simple.ts` |
| 日历热力图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/calendar-heatmap.ts` |
| 日历饼图 | `/tmp/echarts-examples-gh-pages/public/examples/ts/calendar-pie.ts` |

## 示例代码模板

### 读取并使用示例
```python
# 1. 搜索示例
search_files(
    pattern="bar-*.ts",
    path="/tmp/echarts-examples-gh-pages/public/examples/ts"
)

# 2. 读取具体示例
read_file(
    file_path="/tmp/echarts-examples-gh-pages/public/examples/ts/bar-simple.ts"
)

# 3. 提取配置并修改
# 在 execute_python 中参考示例编写代码
data = get_raw_data('{data_id}')
result = {
    "xAxis": {"type": "category", "data": [r['time'] for r in data]},
    "yAxis": {"type": "value"},
    "series": [{
        "type": "bar",
        "data": [r['value'] for r in data]
    }]
}
print(json.dumps(result, ensure_ascii=False))
```

## 注意事项

1. **TypeScript vs Python**：示例是TypeScript语法，需要转换为Python字典
2. **option 结构**：重点关注 `xAxis`、`yAxis`、`series` 三个核心配置
3. **series 类型**：确保 `series[0]['type']` 设置正确的图表类型
4. **数据格式**：根据示例调整数据格式（一维数组/对象数组/嵌套数组）

## 常见问题

**Q1：找不到需要的图表示例？**
A：尝试使用 `grep` 搜索相关关键词，或查看目录结构了解所有可用示例。

**Q2：示例太复杂怎么办？**
A：搜索 `difficulty: 0` 找最简单的示例，或搜索 `category: basic` 找基础图表。

**Q3：如何自定义样式？**
A：在示例基础上修改配置项，如 `color`、`title`、`legend` 等。
