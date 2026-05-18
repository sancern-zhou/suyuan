# ECharts渲染异常修复总结

## 修复时间
2026-05-11

## 问题现象

系统日志显示ECharts渲染失败：
```
playwright_render_failed
TypeError: Cannot read properties of undefined (reading 'get')
    at yx (https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js:45:243582)
    at cartesian2d (https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js:45:242520)
```

## 根本原因

1. **ECharts配置格式问题**：传入的echarts_option可能包含undefined或格式不正确的数据
2. **数据验证不足**：代码没有验证echarts_option的格式就直接传给ECharts
3. **错误处理缺失**：模板中的initChart函数没有try-catch错误处理
4. **文件权限问题**：相关文件属于root用户，无法直接修改

## 修复方案

### 已创建的文件

1. **修复后的HTML模板**：`/tmp/template_fixed.html`
2. **Python代码修复说明**：`/tmp/tool_py_fix.md`
3. **自动修复脚本**：`/tmp/apply_echarts_fix.sh`
4. **完整修复文档**：`/home/xckj/suyuan/ECHARTS_RENDER_FIX.md`

### 修复内容

#### 1. HTML模板修复（template.html）

**新增功能**：
- ✅ try-catch错误处理
- ✅ 验证option格式（series字段）
- ✅ finished事件监听
- ✅ 5秒超时保护
- ✅ 增强console日志输出

**关键代码**：
```javascript
function initChart() {
    try {
        // 验证配置
        if (!window.__ECHARTS_OPTION__) {
            console.error('No ECharts option provided');
            window.__CHART_RENDERED__ = true;
            return;
        }

        var option = window.__ECHARTS_OPTION__;

        // 确保series存在且有效
        if (!option.series || !Array.isArray(option.series)) {
            console.error('Invalid ECharts option: missing or invalid series');
            window.__CHART_RENDERED__ = true;
            return;
        }

        var myChart = echarts.init(chartDom);
        myChart.setOption(option);

        // 渲染完成事件
        myChart.on('finished', function() {
            console.log('Chart rendering finished');
            window.__CHART_RENDERED__ = true;
        });

        // 超时保护
        setTimeout(function() {
            if (!window.__CHART_RENDERED__) {
                console.warn('Chart render timeout');
                window.__CHART_RENDERED__ = true;
            }
        }, 5000);

    } catch (error) {
        console.error('Chart initialization failed:', error);
        window.__CHART_RENDERED__ = true;
    }
}
```

#### 2. Python代码修复（tool.py）

**新增验证逻辑**：
- ✅ 验证echarts_option不为空
- ✅ 验证echarts_option是字典类型
- ✅ 确保series字段存在且是数组
- ✅ 清理series中的无效项
- ✅ 使用default=str处理不可序列化对象

**关键代码**：
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

# 序列化时使用default=str
echarts_json = json.dumps(echarts_option, ensure_ascii=False, default=str)
```

## 应用修复

### 方法1：使用自动脚本（推荐）

```bash
# 运行修复脚本
sudo bash /tmp/apply_echarts_fix.sh
```

脚本会：
1. 自动备份原文件
2. 应用HTML模板修复
3. 提示Python代码需要手动编辑
4. 可选：直接打开nano编辑器

### 方法2：手动修复

#### 步骤1：修复HTML模板

```bash
sudo cp /tmp/template_fixed.html \
   /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/template.html
```

#### 步骤2：修复Python代码

```bash
sudo nano /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py
```

按照 `/tmp/tool_py_fix.md` 中的说明修改第215-241行。

### 方法3：修改文件权限

```bash
# 修改文件所有者
sudo chown -R xckj:xckj \
   /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/

# 然后正常编辑
nano /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py
```

## 验证修复

修复完成后，测试ECharts渲染：

```python
from app.tools.visualization.chart_image_renderer.tool import RenderChartToImageTool
import asyncio

async def test():
    tool = RenderChartToImageTool()

    result = await tool.execute(
        context=None,
        echarts_option={
            "title": {"text": "测试"},
            "xAxis": {"data": ["A", "B", "C"]},
            "yAxis": {},
            "series": [{"type": "bar", "data": [10, 20, 30]}]
        },
        width=800,
        height=500
    )

    print(result)

asyncio.run(test())
```

预期输出：
```
{
    "status": "success",
    "success": True,
    "data": {
        "image_path": "/path/to/chart_xxx.png",
        ...
    },
    "summary": "[OK] 图表渲染完成"
}
```

## 回滚修复

如果修复后出现问题，可以恢复备份：

```bash
# 查看备份文件
ls -la /tmp/echarts_fix_backup_*/

# 恢复HTML模板
sudo cp /tmp/echarts_fix_backup_*/template.html.bak \
   /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/template.html

# 恢复Python代码
sudo cp /tmp/echarts_fix_backup_*/tool.py.bak \
   /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/tool.py
```

## 相关文件

| 文件 | 路径 | 说明 |
|------|------|------|
| 原始模板 | `backend/app/tools/visualization/chart_image_renderer/template.html` | 需要修复 |
| 原始工具 | `backend/app/tools/visualization/chart_image_renderer/tool.py` | 需要修复 |
| 修复模板 | `/tmp/template_fixed.html` | 已创建 |
| 修复说明 | `/tmp/tool_py_fix.md` | 已创建 |
| 修复脚本 | `/tmp/apply_echarts_fix.sh` | 已创建 |
| 完整文档 | `/home/xckj/suyuan/ECHARTS_RENDER_FIX.md` | 已创建 |

## 修复效果

修复后：
- ✅ ECharts配置验证确保数据格式正确
- ✅ 无效数据被自动清理
- ✅ 渲染失败有详细的错误日志
- ✅ 超时保护防止无限等待
- ✅ 异常被正确捕获和处理

## 下一步

1. 运行修复脚本：`sudo bash /tmp/apply_echarts_fix.sh`
2. 手动编辑Python代码（按提示）
3. 重启后端服务
4. 测试ECharts渲染功能
