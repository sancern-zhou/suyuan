# PPT 演示文稿操作指南

## 概述

本项目生成正式或业务型 PPT 时，使用 `create_pptx_with_ppt_master`。同一个工具通过 `operation=create/append/replace/patch/render` 区分新建、追加、替换、局部补丁和渲染预览。底层仍复用同一套 PPT Master 渲染逻辑：Agent 负责内容取舍、页面策略和 `slide_plan`/`plan_patch`，工具负责用 `python-pptx` 确定性绘制、登记产物、渲染 QA 和续改合并。

模板槽位套版路径已从 Agent 工具体系移除。不要调用或建议 `analyze_pptx_template`、`create_pptx_from_template`，也不要回退到旧 deck 结构、底层 PptxGenJS 管线或手动 import PPT 工具类。

## 工具选择

| 任务类型 | 工具 | 说明 |
|---------|------|------|
| 从零生成正式业务 PPT | `create_pptx_with_ppt_master` | 主入口。优先由 Agent 提供 `slide_plan[].shapes` |
| 续改 PPT Master 生成物 | `create_pptx_with_ppt_master(operation="patch")` + `base_plan_path`/`plan_patch` | 读取上一版 plan，只写局部 patch，未涉及页面保持原样 |
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
-> 若预计超过 8 页或 shapes 很多，先 create_pptx_with_ppt_master 生成骨架
-> create_pptx_with_ppt_master(operation="append"/"replace") 按 3-5 页一批插入或替换页面
-> 简短 PPT 可直接 create_pptx_with_ppt_master 绘制完整 PPTX
-> validate_pptx 渲染 PDF/PNG、montage 并生成 QA
-> 结合 QA、单页 PNG 和上一版 slide_plan 写 plan_patch
-> create_pptx_with_ppt_master(operation="patch") 合并 patch 并重绘
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

## 长 PPT 分批生成

当 `slide_plan` 预计超过 8 页、正文页很多、每页 `shapes` 较多，或需要插入大量图表/表格时，不要一次把完整 `slide_plan` 直接内联传给 `create_pptx_with_ppt_master`。长 JSON 参数在流式 tool call 中容易被截断，导致工具参数解析失败。

长 PPT 应按以下流程生成：

1. 首次调用 `create_pptx_with_ppt_master` 只创建骨架 PPT：显式传 `title`、`purpose`、`audience`、`style`，并传短 `outline` 或少量章节/占位页。若已经有完整长 `slide_plan`，先用 `write_file` 写成 JSON 文件，再传 `slide_plan_path`，不要内联长数组。
2. 从返回结果读取最新的 `data.slide_plan_path` 或 `data.page_plan_path`。
3. 每次调用 `create_pptx_with_ppt_master(operation="append"/"replace"/"patch")` 只插入或替换 3-5 页。短批次可用 `batch_slides` + `after_slide`；页面内容较长、shape 较多或包含多表格/图表时，先写 `plan_patch` JSON 文件，再传 `plan_patch_path`。
4. 每一批都必须基于上一批返回的新 `data.slide_plan_path`，不要反复基于最初版本，否则会覆盖或丢失前面批次。
5. 所有批次完成后，再统一检查 `qa_status`、`quality_gate`、`validation.montage_path` 和单页 PNG；需要修复时继续用 `operation="patch"` 和局部 `plan_patch`。

如果某一页的 `shapes` 特别多，应单页或两页一批续改。不要在一次 tool call 中生成 20 页以上的详细 `slide_plan`。

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
2. 根据用户要求、QA 问题和单页 PNG，只写局部修改。连续追加页面时优先使用 `batch_slides` + `after_slide`；复杂替换时使用局部 `plan_patch`。
3. 调用 `create_pptx_with_ppt_master(operation="append", base_plan_path=..., batch_slides=[...], after_slide=...)`，或 `create_pptx_with_ppt_master(operation="patch", base_plan_path=..., plan_patch=...)`。
4. 设置 `quality="standard"` 或 `run_validation=true` 重新验证。
5. 续改结果会返回 `data.next_revision_base_plan_path`，下一批续改优先直接使用该路径。

不要每次重写整份 PPT。未涉及页面由工具从基线 plan 原样保留。

## 已知问题：本地打开时文字自动换行

### 现象

用户下载 PPTX 后在本地 PowerPoint/WPS 中打开，原本单行显示的文字出现自动换行；但拖动文本框后文字又恢复为单行。

### 根因

1. **`wrap="square"` 策略**：文本框默认启用自动换行，PowerPoint 在初始渲染时会对文字执行边界检测，当字体 metrics 有微小偏差时即触发换行。
2. **字体 metrics 不匹配**：服务端测量使用 Noto Sans CJK SC，用户本地使用 Microsoft YaHei，两者 CJK 字符宽度存在 3–8% 差异。
3. **`normAutofit` 延迟触发**：自动缩放文字适应框体的机制需要用户交互（如拖动）后才生效，造成"移动一下就恢复"的现象。

### 规避措施

- **文本框宽度必须留足余量**：单行文本的 `w` 至少为文字估算宽度的 1.5 倍。估算公式：`字符数 × 字号(pt) × 1.1（CJK 安全系数）/ 72`（英寸）。
- **避免框宽"刚好够"**：宁可框宽大一些（不影响视觉，因为文本框默认无背景无边框），也不要让文字宽度接近框宽边界。
- **使用 `tracking`/字间距时额外加宽**：字间距会累积增加总宽度，必须在估算中计入。
- **验证时抽检**：生成后在本地 PowerPoint 中打开检查，特别关注中文诗句、长标题等接近框宽边界的文本。

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
