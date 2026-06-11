# PPT 演示文稿操作指南

## 概述

本项目生成正式或业务型 PPT 时，统一使用 `create_pptx_with_ppt_master`。该工具按 PPT Master 工作流生成可编辑 PPTX：Agent 负责内容取舍、页面策略和 `slide_plan`，工具负责用 `python-pptx` 确定性绘制、登记产物、渲染 QA 和续改合并。

模板槽位套版路径已从 Agent 工具体系移除。不要调用或建议 `analyze_pptx_template`、`create_pptx_from_template`，也不要回退到旧 deck 结构、底层 PptxGenJS 管线或手动 import PPT 工具类。

## 工具选择

| 任务类型 | 工具 | 说明 |
|---------|------|------|
| 从零生成正式业务 PPT | `create_pptx_with_ppt_master` | 主入口。优先由 Agent 提供 `slide_plan[].shapes` |
| 续改 PPT Master 生成物 | `create_pptx_with_ppt_master` + `base_plan_path`/`plan_patch` | 读取上一版 plan，只写局部 patch，未涉及页面保持原样 |
| 读取 PPT 内容 | `read_pptx` | 提取文本、表格、图片信息、备注和基础元数据 |
| 验证 PPT 质量 | `validate_pptx` | 渲染 PDF/PNG、montage，并检查字体、空页、越界、拥挤和文字密度 |

## 从零生成流程

```text
用户需求
-> 明确用途、受众、页数范围、交付口径
-> 查阅资料、读取附件、查询必要数据
-> 形成 QMD 内容底稿或等价结构化大纲
-> 生成必要图表、地图、复杂表格 PNG 资产
-> 将内容规划为 slide_plan[].shapes
-> create_pptx_with_ppt_master 绘制 PPTX
-> validate_pptx 渲染 PDF/PNG、montage 并生成 QA
-> 结合 QA、单页 PNG 和上一版 slide_plan 写 plan_patch
-> create_pptx_with_ppt_master 合并 patch 并重绘
```

用户明确要求“直接生成 PPT”或任务很小、内容已充分明确时，可以跳过内容底稿确认，但仍应保留 QA 和视觉检查。

## PPT Master 规则

调用 `create_pptx_with_ppt_master` 前必须先读：

- `backend/app/tools/office/ppt_master_references/index.md`

再按任务读取：

- `workflow.md`：正式业务 PPT 工作流
- `slide-plan-rules.md`：`slide_plan` 输入合约、renderer 能力边界、QA 字段和示例
- `layout-rules.md`：封面、目录、版式序列和内容密度
- `chart-rules.md`：图表图片、原生图表和数据页规则
- `qa-rules.md`：验证、质量门禁和字体规则
- `output-contract.md`：返回字段和 project 产物检查

## slide_plan 支持的 shape

`slide_plan` 是 body pages 数组。工具自动添加第 1 页封面，所以第一个 `slide_plan` item 会成为第 2 页。

支持的 shape 类型：

- `text`、`textbox`、`title`、`body`
- `image`、`picture`
- `table`
- `rect`、`rectangle`、`card`

坐标单位：

- 默认或 `unit: "in"`：英寸，16:9 页面为 `13.333 x 7.5`
- `unit: "relative"`：`x/w` 为页面宽度比例，`y/h` 为页面高度比例
- `unit: "emu"`：PowerPoint EMU 值

图片 `fit`：

- `contain`：保持比例完整放入目标框
- `cover`：保持比例铺满目标框，使用 PowerPoint crop
- `stretch`：强制拉伸到目标框

表格字段：

- `rows`：二维数组，必填
- `font_size`：表格字号，默认 11
- `header_fill` / `header_color`：表头背景色和文字色
- `cell_fill` / `text_color`：正文单元格背景色和文字色

复杂表格、强样式表格、超宽表格仍建议先渲染为 PNG，再用 `type: "image"` 插入。

## 示例

```python
create_pptx_with_ppt_master(
    title="产品介绍",
    purpose="product_launch",
    audience="客户与销售团队",
    style="business_clean",
    slide_plan=[
        {
            "title": "发布目标",
            "message": "新产品聚焦高价值客户的效率提升场景",
            "shapes": [
                {"type": "title", "x": 0.55, "y": 0.35, "w": 7.5, "h": 0.5, "text": "发布目标", "font_size": 32, "bold": True},
                {"type": "text", "x": 0.58, "y": 0.95, "w": 8.4, "h": 0.35, "text": "新产品聚焦高价值客户的效率提升场景", "font_size": 15, "color": "64748B"},
                {"type": "card", "x": 0.75, "y": 1.75, "w": 3.45, "h": 3.3, "fill": "F8FAFC", "line": "CBD5E1"},
                {"type": "table", "x": 4.8, "y": 1.55, "w": 7.6, "h": 2.1, "rows": [["指标", "当前", "同比"], ["转化率", "18.2%", "+2.1pp"], ["成本", "92", "-6%"]], "font_size": 12},
                {"type": "image", "x": 4.8, "y": 4.0, "w": 7.6, "h": 2.2, "path": "/abs/path/product_chart.png", "fit": "contain"}
            ]
        }
    ],
    output_file="产品介绍.pptx",
    quality="standard",
    run_validation=True
)
```

## 续改

对 PPT Master 生成物继续编辑时：

1. 读取上一次结果里的 `data.slide_plan_path` 或 `data.page_plan_path`。
2. 根据用户要求、QA 问题和单页 PNG，只写局部 `plan_patch`。
3. 调用 `create_pptx_with_ppt_master(base_plan_path=..., plan_patch=...)`。
4. 设置 `quality="standard"` 或 `run_validation=true` 重新验证。

不要每次重写整份 PPT。未涉及页面由工具从基线 plan 原样保留。

## 验证和交付

生成后必须检查：

- `data.file_path`
- `data.project_dir`
- `data.page_plan_path`
- `data.slide_plan_path`
- `data.qa_status`
- `data.quality_gate`
- `data.revision_tasks`
- `data.validation.montage_path`
- `data.validation.pages[].png_path`

`success=true` 只表示文件创建成功。只有 `qa_status=passed` 才能作为可交付版本；如果是 `needs_revision`，应根据结构化 QA 和单页 PNG 继续写 `plan_patch`。
