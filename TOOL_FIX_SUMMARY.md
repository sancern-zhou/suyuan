# 工具异常修复总结

## 修复时间
2026-05-11

## 问题概述

用户要求修复两个工具异常：

### 1. ✅ 报告生成工具 AttributeError（已修复）

**错误**：
```
AttributeError: 'ExpertAnalysis' object has no attribute 'content'
```

**位置**：`backend/app/tools/reporting/generate_tracing_report/tool.py:1115`

**原因**：错误地访问 `report_result.analysis.content`，应该使用 `report_result.analysis.section_content`

**修复**：
```python
# 修复前
if report_result and report_result.analysis and report_result.analysis.content:

# 修复后
if report_result and report_result.analysis and report_result.analysis.section_content:
```

**状态**：✅ 已自动修复完成

---

### 2. ⚠️ ECharts渲染工具失败（需手动修复）

**错误**：
```
playwright_render_failed
TypeError: Cannot read properties of undefined (reading 'get')
    at cartesian2d (https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js:45:242520)
```

**位置**：`backend/app/tools/visualization/chart_image_renderer/tool.py:262`

**原因**：ECharts配置数据格式错误，series中包含undefined或无效数据

**影响**：多个图表渲染失败（7个图表）

---

## 快速修复步骤

### 步骤1：备份文件

```bash
sudo cp /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py \
   /tmp/tool.py.backup.$(date +%Y%m%d_%H%M%S)
```

### 步骤2：编辑文件

```bash
sudo nano /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py
```

### 步骤3：添加数据验证代码

找到 `_render_with_playwright` 方法（约第215行），在 `try:` 块之后添加验证代码：

```python
        try:
            from playwright.async_api import async_playwright

            # ========== 添加数据验证 ==========
            if not echarts_option:
                logger.error("empty_echarts_option")
                return False

            if not isinstance(echarts_option, dict):
                logger.error("invalid_echarts_option_type", type=type(echarts_option))
                return False

            # 确保series存在
            if "series" not in echarts_option:
                logger.warning("echarts_option_missing_series")
                echarts_option = dict(echarts_option)
                echarts_option["series"] = []

            # 清理无效数据
            cleaned_series = []
            for item in echarts_option["series"]:
                if item and isinstance(item, dict):
                    if "data" not in item or item["data"] is None:
                        item["data"] = []
                    cleaned_series.append(item)

            echarts_option["series"] = cleaned_series
            # ========== 验证结束 ==========

            # 读取HTML模板
            template_content = TEMPLATE_HTML.read_text(encoding="utf-8")

            # 修改JSON序列化
            echarts_json = json.dumps(echarts_option, ensure_ascii=False, default=str)
```

### 步骤4：保存并测试

按 `Ctrl+O` 保存，`Ctrl+X` 退出。

---

## 完整修复文档

详细修复说明：`/home/xckj/suyuan/TOOL_FIX_INSTRUCTIONS.md`

## 修复效果

| 问题 | 状态 | 说明 |
|------|------|------|
| 报告生成 AttributeError | ✅ 已修复 | ExpertAnalysis.content → section_content |
| ECharts渲染失败 | ⚠️ 需手动修复 | 需添加数据验证逻辑 |
| HTML模板错误处理 | ⚠️ 可选修复 | 添加try-catch和超时保护 |

## 验证方法

修复后测试：

```python
from app.tools.visualization.chart_image_renderer.tool import RenderChartToImageTool
import asyncio

async def test():
    tool = RenderChartToImageTool()
    result = await tool.execute(
        context=None,
        echarts_option={
            "xAxis": {"data": ["A", "B", "C"]},
            "yAxis": {},
            "series": [{"type": "bar", "data": [10, 20, 30]}]
        }
    )
    print(result)

asyncio.run(test())
```

预期输出：
```
{
    "status": "success",
    "success": True,
    "data": {"image_path": "..."}
}
```

## 相关文件

- 修复说明：`/home/xckj/suyuan/TOOL_FIX_INSTRUCTIONS.md`
- HTML模板：`/tmp/template_fixed.html`
- 修复脚本：`/tmp/apply_echarts_fix.sh`
