# ECharts图表渲染修复

## 问题描述

在生成Word/PPT报告时，图表渲染失败，错误信息：
```
TypeError: Cannot read properties of undefined (reading 'get')
```

## 根本原因

后端直接将v3.1格式的图表数据传递给ECharts渲染器，但ECharts需要的是原生配置格式。

### 数据格式对比

**v3.1格式（后端返回）**：
```json
{
  "type": "bar",
  "title": "污染源贡献",
  "data": {
    "x": ["工业源", "交通源"],
    "y": [45.2, 32.8]
  }
}
```

**ECharts原生格式（前端需要）**：
```json
{
  "xAxis": {
    "type": "category",
    "data": ["工业源", "交通源"]
  },
  "yAxis": {
    "type": "value"
  },
  "series": [{
    "type": "bar",
    "data": [45.2, 32.8]
  }]
}
```

## 解决方案

### 1. 创建转换器

**文件**: `backend/app/utils/chart_v3_to_echarts_converter.py`

功能：将v3.1格式转换为ECharts原生配置，对应前端`ChartPanel.vue`的`buildOption()`函数。

支持的图表类型：
- 基础图表：pie, bar, line, timeseries, radar
- 气象图表：wind_rose, profile, weather_timeseries
- 高级图表：heatmap, stacked_timeseries, pressure_pbl_timeseries
- 3D图表：scatter3d, surface3d, line3d, bar3d, volume3d
- 其他：scatter, facet_timeseries

### 2. 修改报告生成工具

**文件**: `backend/app/tools/reporting/generate_tracing_report/tool.py`

修改`_render_echarts_to_png`方法：
```python
# 使用转换器将v3.1格式转换为ECharts配置
converter = get_chart_v3_converter()
echarts_option = converter.convert(
    chart_type=chart_type,
    chart_data=chart_data,
    title=title,
    meta=meta
)
```

## 架构说明

### 前端（HTML报告）
- 接收v3.1格式数据
- `ChartPanel.vue`动态转换为ECharts配置
- 交互式图表渲染

### 后端（Word/PPT报告）
- 接收v3.1格式数据
- 使用`ChartV3ToEChartsConverter`转换为ECharts配置
- 通过Playwright渲染为静态PNG

## 测试验证

运行测试脚本：
```bash
cd backend
python test_chart_converter.py
```

测试覆盖：
- ✅ 饼图转换
- ✅ 柱状图转换
- ✅ 时序图转换
- ✅ ECharts配置透传

## 相关文件

- `backend/app/utils/chart_v3_to_echarts_converter.py` - 转换器实现
- `backend/app/tools/reporting/generate_tracing_report/tool.py` - 报告生成工具
- `backend/test_chart_converter.py` - 测试脚本
- `frontend/src/components/visualization/ChartPanel.vue` - 前端对应逻辑

## 日期

2026-05-11
