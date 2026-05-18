# ECharts渲染工具修复说明

## 问题1：报告生成工具 AttributeError ✅ 已修复

**错误信息**：
```
AttributeError: 'ExpertAnalysis' object has no attribute 'content'
```

**原因**：
代码错误地使用了 `report_result.analysis.content`，但 `ExpertAnalysis` 类只有 `section_content` 属性。

**修复位置**：
`backend/app/tools/reporting/generate_tracing_report/tool.py` 第1115行

**修复内容**：
```python
# 错误代码
if report_result and report_result.analysis and report_result.analysis.content:

# 修复后
if report_result and report_result.analysis and report_result.analysis.section_content:
```

**状态**：✅ 已自动修复

---

## 问题2：ECharts渲染失败

**错误信息**：
```
playwright_render_failed
TypeError: Cannot read properties of undefined (reading 'get')
    at cartesian2d (https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js:45:242520)
```

**原因**：
传入ECharts的配置数据格式错误，series中包含undefined或格式不正确的数据。

**修复位置**：
`backend/app/tools/visualization/chart_image_renderer/tool.py`

**修复方案**：
在 `_render_with_playwright` 方法中添加数据验证逻辑，确保传入的echarts_option格式正确。

## 手动修复步骤

### 步骤1：备份文件

```bash
sudo cp /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py \
   /tmp/tool.py.backup.$(date +%Y%m%d_%H%M%S)
```

### 步骤2：编辑文件

```bash
sudo nano /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py
```

### 步骤3：找到 _render_with_playwright 方法

按 `Ctrl+W` 搜索 `_render_with_playwright`，找到方法定义（约第215行）。

### 步骤4：在方法开头添加验证逻辑

在 `try:` 块之后，`from playwright.async_api import async_playwright` 之前，添加以下代码：

```python
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
```

### 步骤5：修改JSON序列化

找到 `echarts_json = json.dumps(echarts_option, ensure_ascii=False)` 这一行（约第241行），修改为：

```python
        # 将ECharts配置转为JSON字符串（使用default=str处理不可序列化对象）
        echarts_json = json.dumps(echarts_option, ensure_ascii=False, default=str)
```

### 步骤6：保存并退出

按 `Ctrl+O` 保存，`Ctrl+X` 退出。

### 步骤7：修复HTML模板（可选）

```bash
sudo cp /tmp/template_fixed.html \
   /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/template.html
```

## 验证修复

修复后，重启后端服务并测试图表生成功能。

## 修复效果

修复后：
- ✅ 报告生成不再报 AttributeError
- ✅ ECharts配置数据自动验证和清理
- ✅ 无效数据被自动过滤
- ✅ 渲染失败有详细日志
- ✅ 避免浏览器端JavaScript错误

## 回滚

如果出现问题，可以恢复备份：

```bash
# 查看备份文件
ls -la /tmp/tool.py.backup.*

# 恢复备份
sudo cp /tmp/tool.py.backup.* /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py
```
