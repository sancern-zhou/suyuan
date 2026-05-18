# ECharts渲染异常修复说明

## 问题描述

系统日志显示ECharts渲染失败：
```
playwright_render_failed: Page.evaluate: TypeError: Cannot read properties of undefined (reading 'get')
```

## 根本原因

1. **ECharts配置格式问题**：传入的echarts_option可能包含undefined或格式不正确的数据
2. **数据验证不足**：代码没有验证echarts_option的格式就直接传给ECharts
3. **错误处理缺失**：模板中的initChart函数没有try-catch错误处理

## 修复方案

### 1. 修复HTML模板

创建修复后的模板：`/tmp/template_fixed.html`

**修复内容**：
- ✅ 添加try-catch错误处理
- ✅ 验证option格式（series字段）
- ✅ 添加finished事件监听
- ✅ 添加5秒超时保护
- ✅ 增强console日志输出

**应用方法**：
```bash
sudo cp /tmp/template_fixed.html /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/template.html
```

### 2. 修复Python代码（需要手动编辑）

**文件**：`backend/app/tools/visualization/chart_image_renderer/tool.py`

**修改位置**：第215-241行，`_render_with_playwright`方法

**修改内容**：在注入配置前添加数据验证逻辑

```python
async def _render_with_playwright(
    self,
    echarts_option: Dict[str, Any],
    output_path: str,
    width: int,
    height: int
) -> bool:
    """
    使用Playwright渲染ECharts为PNG

    Args:
        echarts_option: ECharts配置
        output_path: 输出路径
        width: 图片宽度
        height: 图片高度

    Returns:
        是否成功
    """
    try:
        from playwright.async_api import async_playwright

        # 验证ECharts配置格式
        if not echarts_option:
            logger.error("empty_echarts_option")
            return False

        if not isinstance(echarts_option, dict):
            logger.error("invalid_echarts_option_type", type=type(echarts_option))
            return False

        # 确保基本结构存在
        if "series" not in echarts_option:
            logger.warning("echarts_option_missing_series", option=list(echarts_option.keys()))
            echarts_option = dict(echarts_option)  # 创建副本
            echarts_option["series"] = []

        # 验证series是数组
        if not isinstance(echarts_option.get("series"), list):
            logger.warning("echarts_option_invalid_series", type=type(echarts_option.get("series")))
            echarts_option["series"] = []

        # 清理series中的无效数据
        cleaned_series = []
        for item in echarts_option["series"]:
            if item and isinstance(item, dict):
                # 确保data字段存在且有效
                if "data" not in item:
                    item["data"] = []
                elif item["data"] is None:
                    item["data"] = []
                cleaned_series.append(item)
            else:
                logger.warning("invalid_series_item", item=item)

        echarts_option["series"] = cleaned_series

        # 读取HTML模板
        template_content = TEMPLATE_HTML.read_text(encoding="utf-8")

        # 将ECharts配置转为JSON字符串
        echarts_json = json.dumps(echarts_option, ensure_ascii=False, default=str)
```

**关键修改点**：
1. 验证echarts_option不为空
2. 验证echarts_option是字典类型
3. 确保series字段存在且是数组
4. 清理series中的无效项
5. 使用`default=str`处理不可序列化的对象

### 3. 权限修复

如果遇到权限问题，需要修改文件所有者：

```bash
# 修改文件所有者为当前用户
sudo chown -R xckj:xckj /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/

# 或者使用sudo编辑
sudo nano /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py
```

## 测试验证

修复后，测试ECharts渲染是否正常：

```python
# 测试脚本
from app.tools.visualization.chart_image_renderer.tool import RenderChartToImageTool
import asyncio

async def test_render():
    tool = RenderChartToImageTool()

    # 测试配置
    echarts_option = {
        "title": {"text": "测试图表"},
        "xAxis": {"data": ["A", "B", "C"]},
        "yAxis": {},
        "series": [{
            "type": "bar",
            "data": [10, 20, 30]
        }]
    }

    result = await tool.execute(
        context=None,
        echarts_option=echarts_option,
        width=800,
        height=500
    )

    print(result)

asyncio.run(test_render())
```

## 预期效果

修复后：
- ✅ ECharts配置验证确保数据格式正确
- ✅ 无效数据被自动清理
- ✅ 渲染失败有详细的错误日志
- ✅ 超时保护防止无限等待
- ✅ 异常被正确捕获和处理

## 相关文件

- 模板文件：`backend/app/tools/visualization/chart_image_renderer/template.html`
- 工具文件：`backend/app/tools/visualization/chart_image_renderer/tool.py`
- 修复模板：`/tmp/template_fixed.html`
