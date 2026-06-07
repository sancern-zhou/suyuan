# PPT 演示文稿操作指南

## 概述

本指南介绍 PowerPoint 演示文稿（.pptx）的读取、分析和创建方法。

**核心理念**：正式业务 PPT 优先使用 PPT Master 工作流，先锁定目标、结构、风格和版式，再逐页绘制并质检。

---

## 核心原则

### 1. 工具选择优先级

| 任务类型 | 推荐工具 | 理由 |
|---------|---------|------|
| **业务型PPT生成** | `create_pptx_with_ppt_master` | 按目标、大纲、风格、版式锁定、逐页绘制、QA 的生产流程生成 |
| **基于模板创建PPT** | `create_pptx_from_template` | 保持设计风格，推荐 |
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

### PPT Master 优先原则

生成正式或业务型 PPT 时，优先使用 `create_pptx_with_ppt_master`。不要再使用旧 deck 结构或底层 PptxGenJS 管线。Agent 应先把需求整理为用途、受众、风格和结构化大纲，由工具创建 project、设计规格、版式锁定、逐页 SVG 草稿和可编辑 PPTX。

调用前必须先读取：

- `backend/app/tools/office/ppt_master_references/index.md`

再按任务渐进读取所需规则：

- `workflow.md`：正式业务 PPT 工作流
- `layout-rules.md`：封面、目录、版式序列和内容密度
- `chart-rules.md`：图表图片、原生图表和数据页规则
- `qa-rules.md`：验证、质量门禁和字体规则
- `output-contract.md`：返回字段和 project 产物检查

**禁止绕过工具入口**：生成新业务 PPT 时，必须直接调用 `create_pptx_with_ppt_master` 或 `create_pptx_from_template`。不要使用 `execute_python` 手动 import PPT 工具类，也不要直接调用旧 renderer。`execute_python` 只能用于前置数据处理、生成图片资产，或对已有 PPT 做专门工具无法覆盖的局部兼容处理。

`create_pptx_with_ppt_master` 的输入是业务目标和大纲，不接收 `suyuan.deck.v2`。输出会包含：

- `file_path`：生成的 `.pptx`
- `project_dir`：PPT Master project 目录
- `design_spec_path`：设计规格
- `spec_lock_path`：母版/版式锁定
- `page_plan_path`：逐页计划
- `svg_pages`：逐页 SVG 草稿
- `quality_gate`：工作流质量门禁
- `qa_status`：`passed | needs_revision | qa_failed`
- `revision_tasks`：QA 生成的下一轮编辑任务

具体硬性约束统一维护在 `ppt_master_references/`，不要在技能文档中复制工具约束。

示例：

```json
{
  "title": "濮阳市智慧环保建设项目二期实施方案",
  "purpose": "government_briefing",
  "audience": "政府决策部门",
  "style": "government_consulting",
  "outline": [
    {"title": "建设目标", "points": ["补强感知能力", "升级平台能力", "形成闭环治理"]},
    {
      "title": "能力架构",
      "chart": {"type": "image", "image_path": "/home/xckj/suyuan/backend/backend_data_registry/images/能力架构.png"},
      "points": ["数据底座", "预警研判", "调度指挥"]
    },
    {"title": "实施路径", "points": ["一期梳理", "二期建设", "运营考核"]}
  ],
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

### 4. validate_pptx - 验证PPT质量

**功能**：渲染 PPTX，生成 PDF/PNG、montage 总览图和 QA 报告，检查字体、空白页、形状越界、渲染溢出、规则型视觉质量等问题。

**用法**：
```python
validate_pptx(
    path="演示文稿.pptx",
    expected_fonts=["Microsoft YaHei"],
    render_overflow_check=True
)
```

**返回结果**：
```json
{
  "success": true,
  "data": {
    "success": false,
    "montage_path": "backend/backend_data_registry/presentations/qa/report_xxx/montage.png",
    "report_path": "backend/backend_data_registry/presentations/qa/report_xxx/report.json",
    "issue_count": 2,
    "issues": [
      {
        "type": "rendered_low_margin",
        "slide": 4
      }
    ]
  },
  "summary": "PPT验证完成：演示文稿.pptx，发现 2 个问题"
}
```

**视觉分析流程约束**：

- 只要 `validate_pptx` 返回了 `data.montage_path`，必须继续调用 `analyze_image(path=data.montage_path, operation="analyze", prompt="...")`。
- 视觉分析重点检查：整体观感、页面拥挤、图表可读性、标题层级、留白、页面是否错位、图片是否压缩变形、是否存在明显模板残留。
- `analyze_image` 发现的问题要进入下一轮 PPT 优化任务；不要把只通过规则 QA、但视觉分析明显不佳的 PPT 当作最终交付。

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

### 场景 2：正式业务PPT（无模板）

```python
create_pptx_with_ppt_master(
    title="产品介绍",
    purpose="product_launch",
    audience="客户与销售团队",
    style="business_clean",
    outline=[
        {"title": "发布目标", "points": ["明确产品定位", "突出核心价值"]},
        {"title": "核心特性", "points": ["高性能处理器", "超长续航", "创新设计"]},
        {"title": "上市计划", "points": ["渠道准备", "客户触达", "售后保障"]}
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

❌ **错误**：有模板或正式汇报需求但试图走旧 `create_pptx` 从头创建
```python
# 旧工具已删除，设计风格也不可控
create_pptx(title="...", slides=[...])
```

✅ **正确**：有模板用 `create_pptx_from_template`；无模板的正式业务 PPT 用 `create_pptx_with_ppt_master`
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

**原因**：使用旧一步式渲染或缺少目标、风格、版式锁定和逐页 QA。

**解决**：
1. 正式业务 PPT 使用 `create_pptx_with_ppt_master`
2. 有模板时使用 `create_pptx_from_template`
3. 生成后使用 `validate_pptx` 检查 PDF/PNG 预览、字体、溢出和版式问题
4. 对 `montage_path` 调用 `analyze_image` 做视觉质量检查，并按结果继续迭代

---

## 相关资源

- [python-pptx 文档](https://python-pptx.readthedocs.io/)
- [PPT Master Reference Index](ppt_master_references/index.md)
