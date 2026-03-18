# Office 文档修改决策树

## 快速决策流程

```
用户请求修改文档
      │
      ▼
┌─────────────────┐
│  1. 读取文档    │ ← 必须步骤！
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. 分析需求    │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌──────┐  ┌──────────┐
│ 单个  │  │  多个    │
│ 替换  │  │  替换    │
└───┬──┘  └─────┬────┘
    │            │
    ▼            ▼
┌──────┐    ┌──────────┐
│精确?  │    │批量替换  │
└──┬───┘    │batch_    │
   │        │replace   │
   ├─Yes──► └──────────┘
   │
   ├─No──► ┌──────────────────┐
           │search_and_replace │
           │（支持通配符）      │
           └──────────────────┘
```

## 场景决策表

| 场景 | 操作 | 示例 |
|------|------|------|
| 删除一个精确文本 | `replace` | 删除"错误数据" |
| 替换一个精确文本 | `replace` | "旧版本"→"新版本" |
| 删除所有相似文本 | `search_and_replace` | 删除所有"*待定*" |
| 替换多个不同文本 | `batch_replace` | {"2024":"2025", "Q1":"Q2"} |
| 使用通配符匹配 | `search_and_replace` | "*臭氧*浓度*" |

## 参数映射表

### Word 工具

| 用户意图 | operation | 主要参数 | 示例 |
|---------|-----------|---------|------|
| 删除文本 | replace | find="文本", replace="" | find="错误", replace="" |
| 替换文本 | replace | find="旧", replace="新" | find="旧值", replace="新值" |
| 模糊删除 | search_and_replace | search_text="*模式*", use_wildcards=true | search_text="*待定*", use_wildcards=true |
| 批量替换 | batch_replace | replacements={"旧1":"新1", "旧2":"新2"} | replacements={"A":"B", "C":"D"} |

### PowerPoint 工具

| 用户意图 | operation | 主要参数 | 示例 |
|---------|-----------|---------|------|
| 删除文本 | replace | find="文本", replace="" | find="待定", replace="" |
| 模糊删除 | search_and_replace | search_text="模式", match_case=false | search_text="待定", replace_text="" |
| 替换文本 | replace | find="旧", replace="新" | find="2024", replace="2025" |

### Excel 工具

| 用户意图 | operation | 主要参数 | 示例 |
|---------|-----------|---------|------|
| 修改单元格 | write_cell | cell_address, value | cell_address="A1", value="新值" |
| 修改区域 | write_range | range_address, data | range_address="A1:B10", data=[[...]] |

## 错误恢复流程

```
操作失败
    │
    ▼
┌─────────────────┐
│  检查错误信息   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌─────────┐ ┌─────────────┐
│ 文本不  │ │  参数错误   │
│ 存在    │ │             │
└────┬────┘ └──────┬──────┘
     │            │
     ▼            ▼
┌─────────┐ ┌─────────────┐
│ 重新读取 │ │ 修正参数    │
│ 精确文本 │ │ 重试        │
└─────────┘ └─────────────┘
```

## LLM Prompt 建议

### 在 System Prompt 中添加

```markdown
## Office 文档修改规则

### 必须遵守的流程
1. **先读取文档** - 使用 read/list_slides/list_sheets 操作
2. **精确定位文本** - 使用文档中实际存在的文本（包括标点、空格）
3. **选择正确操作** - replace（精确）/search_and_replace（模糊）/batch_replace（多个）

### 常见错误
❌ 直接猜测文本内容 → ✅ 先读取确认
❌ 使用模糊文本进行精确替换 → ✅ 使用 search_and_replace
❌ 修改后不保存 → ✅ 工具自动保存（或使用 save_as 参数）

### 工具选择
- **Word 文档**: word_processor
- **PowerPoint**: ppt_processor
- **Excel**: excel_processor
```

### 在工具描述中强调

```python
description = """
读取和编辑 Word 文档（仅 Windows）。

⚠️ 重要：修改文档前必须先读取内容确认文本！

支持的操作：
- read: 读取文档（修改前必须执行）
- replace: 精确替换（必须使用文档中实际存在的文本）
- search_and_replace: 模糊匹配替换（支持通配符）
- batch_replace: 批量替换多个文本
- tables: 读取表格
- stats: 获取统计信息
"""
```

## 调试检查清单

当 Agent 调用 Office 工具时，检查以下内容：

### ✓ 读取阶段
- [ ] 是否先调用了 read/list_slides/list_sheets？
- [ ] 是否从返回结果中提取了精确文本？

### ✓ 执行阶段
- [ ] 选择的操作类型是否正确（replace/search_and_replace/batch_replace）？
- [ ] find/search_text 是否使用了文档中的精确文本？
- [ ] replace/replace_text 是否设置正确（空字符串表示删除）？
- [ ] 是否需要使用通配符（use_wildcards=true）？

### ✓ 验证阶段
- [ ] 是否检查了返回的替换次数？
- [ ] 替换次数是否符合预期？
- [ ] 如果需要，是否进行了二次读取确认？

## 示例对话

### 正确示例 1

```
用户：删除文档中的"待定数据"

Agent：
1. 读取文档: operation="read", start_index=0, end_index=100
2. 发现文档中有"待定数据"、"待定项目"、"待定："
3. 调用模糊删除: operation="search_and_replace", search_text="*待定*", use_wildcards=true
4. 返回: 删除了 15 处包含"待定"的文本
```

### 错误示例 1

```
用户：删除文档中的"2025年1月数据"

Agent：
❌ 直接调用: operation="replace", find="2025年1月数据", replace=""
问题: 文档中可能是"2025年1月份数据"或"2025-01数据"

正确做法：
1. 先读取文档确认精确文本
2. 使用确认的文本执行替换
```

### 错误示例 2

```
用户：把所有"O3"改为"O₃"

Agent：
❌ 调用: operation="replace", find="O3", replace="O₃"
问题: 会把"CO2"、"NO3"等也错误替换

正确做法：
1. 使用 search_and_replace: operation="search_and_replace"
2. 使用通配符: search_text=" O3 ", replace_text=" O₃ "（添加空格避免误替换）
3. 或者使用更精确的模式: search_text="<O3>"
```
