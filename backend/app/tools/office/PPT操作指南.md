# PPT 演示文稿操作指南

## 概述

本指南介绍 PowerPoint 演示文稿（.pptx）的读取、分析和创建方法。

**核心理念**：优先使用基于模板的方式创建PPT，保持设计风格一致性。

---

## 核心原则

### 1. 工具选择优先级

| 任务类型 | 推荐工具 | 理由 |
|---------|---------|------|
| **业务型PPT生成** | `create_pptx_from_deck` | Agent 只写业务结构，代码负责版式和质量 |
| **基于模板创建PPT** | `create_pptx_from_template` | 保持设计风格，推荐 |
| 从头创建PPT | `create_pptx` | 无模板时使用 |
| 读取PPT内容 | `read_pptx` | 了解幻灯片内容 |
| 分析模板结构 | `analyze_pptx_template` | 获取可替换槽位 |
| 验证PPT质量 | `validate_pptx` | 检查设计质量 |

### 2. 创建前必须分析

在使用任何PPT创建工具之前，**必须**先执行：
```python
# 第一步：分析模板（如果使用模板）
analyze_pptx_template(path="模板.pptx")

# 第二步：根据分析结果创建PPT
```

---

## 工具详解

### Deck Spec 优先原则

生成正式或业务型 PPT 时，优先使用 `create_pptx_from_deck`，不要让 Agent 直接从零构造低层 PPT 元素。Agent 应输出 `suyuan.deck.v2` 设计稿，由工具转换成 `create_pptx` 可渲染结构。

调用前必须先读取：

- `backend/app/tools/office/deck/references/index.md`
- `backend/app/tools/office/deck/references/archetypes.md`
- `backend/app/tools/office/deck/references/checklist.md`
- 与 `deck_type` 对应的参考文档

**禁止绕过工具入口**：生成新 PPT 时，必须直接调用 `create_pptx_from_deck`、`create_pptx_from_template` 或 `create_pptx` 工具。不要使用 `execute_python` 手动 import `CreatePptxFromDeckTool`、`CreatePptxTool`，也不要在 `execute_python` 中直接调用 PptxGenJS renderer。`execute_python` 只能用于前置数据处理、生成图片资产，或对已有 PPT 做专门工具无法覆盖的局部兼容处理。

`create_pptx_from_deck` 2.0 不兼容 `suyuan.deck.v1`，也不接受底层 `create_pptx` 的 `title`、`bullets`、`table`、`image_full` slide type。低层绘图结构请直接使用 `create_pptx`。

支持的 slide archetype：

```text
cover, agenda, section_divider, executive_summary, key_message,
three_column_points, metric_dashboard, comparison_matrix, timeline,
roadmap, process_flow, architecture_overview, data_flow, map_story,
chart_story, evidence_table, risk_matrix, budget_breakdown,
implementation_plan, responsibility_matrix, closing_actions
```

除 `cover`、`agenda`、`section_divider`、`appendix` 外，每页必须包含至少一种视觉证据或结构化内容：`content.items`、`content.steps`、`metrics`、`table`、`chart` 或 `visual`。

`chart_story` 的 `chart` 字段用于生成 PPT 内原生图表。模板填充请使用 `create_pptx_from_template`。

示例：

```json
{
  "deck": {
    "version": "suyuan.deck.v2",
    "deck_type": "implementation_proposal",
    "title": "濮阳市智慧环保建设项目二期实施方案",
    "audience": "government_decision_makers",
    "tone": "formal, evidence-led, implementation-focused",
    "slides": [
      {
        "id": "s01",
        "archetype": "cover",
        "title": "濮阳市智慧环保建设项目二期实施方案",
        "subtitle": "智慧感知、平台协同与闭环治理能力建设"
      },
      {
        "id": "s02",
        "archetype": "three_column_points",
        "title": "二期建设聚焦三类能力",
        "message": "围绕感知补强、平台升级、业务闭环和运营考核形成综合治理能力。",
        "content": {
          "items": [
            {"title": "感知补强", "body": "完善空气、水、源、视频等多源监测能力"},
            {"title": "平台升级", "body": "建设统一数据底座、预警研判和调度指挥能力"},
            {"title": "闭环治理", "body": "形成发现、研判、派单、处置、复核全过程闭环"}
          ]
        }
      }
    ]
  },
  "quality": "standard",
  "run_validation": true
}
```

### 1. read_pptx - 读取 PPT 内容

**功能**：读取 .pptx 文件的完整内容（文本、布局、图像）

**用法**：
```python
read_pptx(
    path="演示文稿.pptx",
    max_slides=50  # 可选：限制幻灯片数量
)
```

**返回结果**：
```json
{
  "success": true,
  "data": {
    "slides": [
      {
        "index": 0,
        "layout": "Title Slide",
        "title": "标题",
        "content": [...]
      }
    ]
  },
  "summary": "共 25 页幻灯片"
}
```

---

### 2. analyze_pptx_template - 分析模板结构

**功能**：分析PPT模板，识别可替换的槽位（slot_id）

**用法**：
```python
analyze_pptx_template(
    path="模板.pptx",
    include_layouts=True,   # 可选：包含布局信息
    write_report=True       # 可选：写入分析报告
)
```

**返回结果**：
```json
{
  "success": true,
  "data": {
    "slots": [
      {
        "slot_id": "s001_slot001",
        "slide_index": 0,
        "type": "title",
        "current_text": "原标题"
      }
    ]
  },
  "summary": "发现 15 个可替换槽位"
}
```

---

### 3. create_pptx_from_template - 基于模板创建（推荐）

**功能**：基于现有PPT模板，通过替换槽位生成新PPT

**适用场景**：
- ✅ 有现成的模板文件
- ✅ 需要保持统一的设计风格
- ✅ 批量生成相似结构的PPT
- ✅ 公司标准模板

**用法**：
```python
create_pptx_from_template(
    template_path="模板.pptx",
    replacements={
        "s001_slot001": "新标题",
        "s001_slot002": "副标题内容",
        "s002_slot003": "正文内容..."
    },
    output_file="新演示文稿.pptx"
)
```

**完整示例**：
```python
# 第一步：分析模板
analysis = analyze_pptx_template(path="公司模板.pptx")

# 第二步：提取槽位
slots = {slot["slot_id"]: slot["current_text"] for slot in analysis["data"]["slots"]}

# 第三步：替换内容
create_pptx_from_template(
    template_path="公司模板.pptx",
    replacements={
        "s001_slot001": "2026年度工作总结",
        "s002_slot002": "项目背景与目标",
        "s002_slot003": "本年度主要成果包括..."
    },
    output_file="年度总结_2026.pptx"
)
```

---

### 4. create_pptx - 从头创建（不推荐）

**功能**：使用 PptxGenJS 从结构化JSON一步生成可编辑PPTX

**适用场景**：
- ⚠️ 仅在**没有模板**时使用
- ⚠️ 需要完全自定义设计
- ⚠️ 快速原型制作

**用法**：
```python
create_pptx(
    title="演示文稿标题",
    slides=[
        {
            "type": "title",
            "title": "主标题",
            "subtitle": "副标题"
        },
        {
            "type": "bullets",
            "title": "要点列表",
            "items": ["要点1", "要点2", "要点3"]
        },
        {
            "type": "image",
            "title": "配图说明",
            "image_path": "/path/to/image.png"
        }
    ],
    output_file="新演示文稿.pptx"
)
```

> 注意：`create_pptx` 也必须通过正式工具调用入口执行。不要用 `execute_python` 拼接 `slides` 后手动调用工具类或 renderer；业务型 PPT 应优先上移为 `create_pptx_from_deck` 的 `suyuan.deck.v2` 设计稿。

**支持的幻灯片类型**：
- `title` - 标题页
- `bullets` - 要点列表
- `key_message` - 核心信息
- `image` - 图片页
- `chart` - 图表页
- `table` - 表格页
- `comparison` - 对比页
- `timeline` - 时间线
- `process` - 流程图

---

### 5. validate_pptx - 验证PPT质量

**功能**：检查PPT的设计质量（字体、颜色、布局等）

**用法**：
```python
validate_pptx(
    path="演示文稿.pptx",
    quality_level="standard"  # basic | standard | professional
)
```

**返回结果**：
```json
{
  "success": true,
  "data": {
    "score": 85,
    "issues": [
      {
        "type": "font",
        "message": "幻灯片3使用了过多字体（5种）"
      }
    ]
  },
  "summary": "质量评分：85/100，发现 2 个问题"
}
```

---

## 标准操作流程

### 场景 1：基于模板创建PPT（推荐）

```python
# 第一步：分析模板
analyze_pptx_template(path="公司标准模板.pptx")

# 第二步：基于分析结果创建PPT
create_pptx_from_template(
    template_path="公司标准模板.pptx",
    replacements={
        "s001_slot001": "项目汇报",
        "s002_slot002": "背景介绍",
        "s002_slot003": "本项目旨在..."
    },
    output_file="项目汇报.pptx"
)

# 第三步：验证质量
validate_pptx(path="项目汇报.pptx")
```

---

### 场景 2：从头创建PPT（无模板）

```python
create_pptx(
    title="产品介绍",
    slides=[
        {
            "type": "title",
            "title": "新产品发布",
            "subtitle": "2026年度旗舰产品"
        },
        {
            "type": "bullets",
            "title": "核心特性",
            "items": [
                "特性1：高性能处理器",
                "特性2：超长续航",
                "特性3：创新设计"
            ]
        },
        {
            "type": "image",
            "title": "产品外观",
            "image_path": "/path/to/product.png"
        }
    ],
    output_file="产品介绍.pptx"
)
```

---

### 场景 3：批量生成PPT

```python
from pathlib import Path

# 分析一次模板
template_analysis = analyze_pptx_template(path="月报模板.pptx")

# 批量生成
for month in ["1月", "2月", "3月"]:
    create_pptx_from_template(
        template_path="月报模板.pptx",
        replacements={
            "s001_slot001": f"{month}工作总结",
            "s002_slot002": f"{month}主要成果",
            "s002_slot003": f"{month}完成..."
        },
        output_file=f"{month}月报.pptx"
    )
```

---

## 常见错误及解决

### 错误 1：工具选择不当

❌ **错误**：有模板但用 `create_pptx` 从头创建
```python
# 浪费时间，设计风格不一致
create_pptx(title="...", slides=[...])
```

✅ **正确**：使用 `create_pptx_from_template`
```python
# 保持设计风格，更高效
create_pptx_from_template(
    template_path="模板.pptx",
    replacements={...}
)
```

---

### 错误 2：未分析模板直接创建

❌ **错误**：不知道 slot_id 就尝试替换
```python
# 这样会失败，slot_id 不存在
create_pptx_from_template(
    template_path="模板.pptx",
    replacements={"slot001": "内容"}  # 错误的slot_id
)
```

✅ **正确**：先分析再创建
```python
# 第一步：获取正确的 slot_id
analysis = analyze_pptx_template(path="模板.pptx")

# 第二步：使用正确的 slot_id
create_pptx_from_template(
    template_path="模板.pptx",
    replacements={"s001_slot001": "内容"}  # 正确
)
```

---

### 错误 3：槽位类型不匹配

❌ **错误**：给图片槽位传入文本
```python
# 这样会失败或显示异常
create_pptx_from_template(
    template_path="模板.pptx",
    replacements={"s003_image_slot": "文本内容"}  # 错误类型
)
```

✅ **正确**：传入正确类型的值
```python
create_pptx_from_template(
    template_path="模板.pptx",
    replacements={"s003_image_slot": "/path/to/image.png"}  # 正确
)
```

---

## 最佳实践

### 1. 创建前检查清单

- [ ] 是否有现成模板？（有 → 用 create_pptx_from_template）
- [ ] 是否已分析模板了解槽位？
- [ ] slot_id 是否正确？
- [ ] 替换内容类型是否匹配？

### 2. 设计原则

- **一页一核心**：每页幻灯片只讲一个核心观点
- **图文并茂**：避免纯文字堆砌
- **配色统一**：使用主题色，不超过3种主色
- **字体一致**：标题字体和正文字体保持一致

### 3. 图片处理

```python
# 优先使用图片类型幻灯片
{
    "type": "image",
    "title": "配图说明",
    "image_path": "/path/to/image.png",
    "caption": "图片说明文字"
}
```

### 4. 批量生成建议

```python
# 复用分析结果，避免重复分析
template_analysis = analyze_pptx_template(path="模板.pptx")

for data in dataset:
    create_pptx_from_template(
        template_path="模板.pptx",
        replacements=data,
        output_file=f"输出_{data['id']}.pptx"
    )
```

---

## 故障排查

### 问题：slot 替换失败

```
warning: template_slot_replace_failed
error: 目标槽位不是文本框
```

**原因**：槽位类型与传入值类型不匹配

**解决**：
1. 检查 `analyze_pptx_template` 返回的槽位类型
2. 确保传入值类型正确（文本、图片、表格）

---

### 问题：模板文件不存在

```
FileNotFoundError: 模板文件不存在
```

**解决**：
1. 检查文件路径是否正确
2. 使用绝对路径而非相对路径
3. 确认文件扩展名是 .pptx

---

### 问题：生成的PPT设计混乱

**原因**：使用 `create_pptx` 从头创建，未指定主题

**解决**：
1. 使用 `create_pptx_from_template` 基于模板创建
2. 或在 `create_pptx` 中指定 `theme` 参数

---

## 相关资源

- [python-pptx 文档](https://python-pptx.readthedocs.io/)
- [PptxGenJS 文档](https://gitbrent.github.io/PptxGenJS/)
- Anthropic PPT Skill: https://github.com/anthropics/skills/tree/main/skills/ppt
