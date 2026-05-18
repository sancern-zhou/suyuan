# 报告结构优化说明

## 修改时间
2026-05-11

## 修改文件
`backend/app/tools/reporting/generate_tracing_report/tool.py`

## 修改概述
重构报告生成逻辑，简化章节结构，消除内容重复，过滤元认知文本。

## 主要修改

### 1. 简化报告结构

**修改前**：
- 1.1 执行摘要（包含结论和建议）
- 1.2 气象条件分析（包含图表）
- 1.3 污染物组分分析（包含图表）
- 1.4 数据可视化（空章节）
- 1.5 综合分析
- 1.6 综合分析结论（包含完整分析内容）

**修改后**：
- 综合分析（单一章节）
  - 气象与传输分析
  - 污染物组分分析
  - 主要结论
  - 控制建议

### 2. 新增功能

#### 2.1 元认知文本过滤
```python
def _filter_meta_cognitive_text(self, text: str) -> str
```

**过滤模式**：
- "嗯，用户要求我..."
- "我需要先理解..."
- "现在我需要处理..."
- "让我仔细分析..."
- 等LLM思考过程的标记

**保留内容**：
- 正式章节标题（## ###）
- 实际分析内容
- 图表和数据描述

#### 2.2 企业分布地图自动插入
```python
def _insert_enterprise_maps(
    self,
    content: str,
    visuals_by_expert: Dict[str, List[Dict[str, Any]]],
    amap_key: str
) -> str
```

**插入位置**：气象分析 → 图表解析 → 轨迹图之后

**插入内容**：
- 上风向企业分布地图标题
- 交互式地图（HTML格式）
- 静态地图图片（DOCX/PPTX格式）

#### 2.3 简化综合分析生成
```python
def _generate_simplified_analysis(
    self,
    pipeline_result,
    visuals_by_expert: Dict[str, List[Dict[str, Any]]]
) -> str
```

**功能**：
- 提取 report 专家的分析内容
- 过滤元认知文本
- 插入企业分布地图
- 添加报告元数据

### 3. 修改的方法

#### _generate_qmd_content
- **删除**：执行摘要章节生成
- **删除**：专家分析章节生成
- **删除**：独立结论章节生成
- **新增**：调用 `_generate_simplified_analysis`

### 4. 保留的方法

以下方法保留未修改，但不再被调用（保留以备将来使用）：
- `_generate_expert_sections`
- `_generate_final_conclusion`

## 修改效果

### 内容质量提升
- ✅ 消除章节间内容重复
- ✅ 移除元认知文本泄露
- ✅ 统一章节结构

### 地图显示修复
- ✅ 地图背景正常显示（features + mapStyle）
- ✅ 企业分布地图插入到合适位置
- ✅ 支持交互式和静态两种格式

### 空章节处理
- ✅ 自动跳过没有内容的专家章节
- ✅ 避免生成空章节

## 测试验证

运行测试脚本验证过滤功能：
```bash
cd /home/xckj/suyuan/backend
python test_filter.py
```

## 后续建议

1. **Prompt优化**：从源头避免LLM生成元认知文本
2. **章节结构**：考虑进一步优化章节标题层级
3. **图表插入**：考虑智能识别最佳插入位置

## 相关文件

- 地图模板：`backend/app/tools/visualization/chart_image_renderer/amap_template.html`
- 报告渲染器：`backend/app/services/quarto_report_renderer.py`
- 测试脚本：`backend/test_filter.py`
