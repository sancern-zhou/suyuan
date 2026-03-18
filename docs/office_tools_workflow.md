# Agent 修改 Office 文档的正确工具调用流程

## 概述

本文档详细说明了 Agent（LLM）在需要修改 Word、PowerPoint、Excel 文档时应该遵循的正确工具调用流程。

## 核心原则

### 1. 先读取，后修改
**必须先读取文档内容，确认需要修改的文本，然后再执行修改操作。**

❌ **错误流程**：
```
用户：删除文档中的"错误数据"
Agent：直接调用 replace 操作删除"错误数据"
```

✅ **正确流程**：
```
用户：删除文档中的"错误数据"
Agent：
  1. 调用 read 操作，读取文档内容
  2. 分析文档，找到"错误数据"的确切位置和格式
  3. 调用 replace/search_and_replace 操作，删除"错误数据"
  4. （可选）再次读取确认修改成功
```

### 2. 使用精确的文本匹配
**必须使用文档中实际存在的精确文本，包括标点符号、空格、大小写等。**

❌ **错误示例**：
```json
{
  "operation": "replace",
  "find": "2025年1月22日成都市臭氧8小时滑动浓度（O3_8h）为41 μg/m³",
  "replace": ""
}
```
问题：文档中可能是"臭氧滑动8小时最大浓度"，或者单位是"微克/立方米"

✅ **正确示例**：
```json
{
  "operation": "read",
  "start_index": 0,
  "end_index": 10
}
// 读取后发现实际文本是"臭氧滑动8小时最大浓度（O3_8h）为41微克/立方米"

{
  "operation": "replace",
  "find": "臭氧滑动8小时最大浓度（O3_8h）为41微克/立方米",
  "replace": ""
}
```

### 3. 选择合适的替换操作
根据具体场景选择 `replace`、`search_and_replace` 或 `batch_replace`：

| 操作 | 适用场景 | 特点 |
|------|---------|------|
| `replace` | 已知精确文本，单个替换 | 最简单、最可靠 |
| `search_and_replace` | 需要模糊匹配、通配符 | 支持通配符、正则表达式 |
| `batch_replace` | 多个不同的替换 | 一次性执行多个替换 |

---

## Word 文档修改流程

### 场景 1：删除特定文本（已知精确文本）

```json
{
  "thought": "用户要求删除文档中的'臭氧滑动8小时最大浓度（O3_8h）为41微克/立方米'。我需要先读取文档确认该文本存在，然后执行删除操作。",
  "reasoning": "已经在前面的对话中读取过文档，确认该文本存在。现在使用 replace 操作，将 find 参数设为要删除的文本，replace 参数设为空字符串即可删除。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "word_processor",
    "args": {
      "file_path": "D:\\溯源\\报告模板\\2025年臭氧垂直报告7-ok - 副本.docx",
      "operation": "replace",
      "find": "臭氧滑动8小时最大浓度（O3_8h）为41微克/立方米",
      "replace": ""
    }
  }
}
```

**返回结果**：
```json
{
  "status": "success",
  "success": true,
  "data": {
    "replacements": 1,
    "output_file": "D:\\溯源\\报告模板\\2025年臭氧垂直报告7-ok - 副本.docx"
  },
  "summary": "替换了 1 处 '臭氧滑动8小时最大浓度（O3_8h）为41微克/立方米' -> ''"
}
```

### 场景 2：删除所有相似表述（模糊匹配）

```json
{
  "thought": "用户要求删除所有关于臭氧浓度的相似表述，包括'臭氧滑动8小时最大浓度'、'O3_8h浓度为41微克/立方米'等多种表述。",
  "reasoning": "这些表述虽然格式不同，但都包含关键词'臭氧'和浓度数值。使用 search_and_replace 操作配合通配符可以匹配所有相似表述。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "word_processor",
    "args": {
      "file_path": "D:\\溯源\\报告模板\\2025年臭氧垂直报告7-ok - 副本.docx",
      "operation": "search_and_replace",
      "search_text": "*臭氧*浓度*微克/立方米*",
      "replace_text": "",
      "use_wildcards": true
    }
  }
}
```

**返回结果**：
```json
{
  "status": "success",
  "success": true,
  "data": {
    "replacements": 5,
    "matches": [
      "臭氧滑动8小时最大浓度（O3_8h）为41微克/立方米",
      "O3_8h浓度为41微克/立方米",
      "臭氧8小时浓度为41微克/立方米"
    ],
    "output_file": "D:\\溯源\\报告模板\\2025年臭氧垂直报告7-ok - 副本.docx"
  },
  "summary": "搜索并替换完成，找到 5 处匹配，替换了 5 处 '*臭氧*浓度*微克/立方米*' -> ''"
}
```

### 场景 3：批量修改多个文本

```json
{
  "thought": "用户要求将文档中的所有'μg/m³'替换为'µg/m³'（正确的微克符号），同时将'O3'改为'O₃'（下标）。",
  "reasoning": "有两个独立的替换任务，使用 batch_replace 操作一次性完成，避免多次打开文档。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "word_processor",
    "args": {
      "file_path": "D:\\溯源\\报告模板\\报告.docx",
      "operation": "batch_replace",
      "replacements": {
        "μg/m³": "µg/m³",
        "O3": "O₃"
      }
    }
  }
}
```

**返回结果**：
```json
{
  "status": "success",
  "success": true,
  "data": {
    "results": [
      {"old": "μg/m³", "new": "µg/m³", "count": 25},
      {"old": "O3", "new": "O₃", "count": 18}
    ],
    "total_replacements": 43,
    "output_file": "D:\\溯源\\报告模板\\报告.docx"
  },
  "summary": "批量替换完成，共 43 处"
}
```

### 场景 4：修改后保存为新文件

```json
{
  "thought": "用户要求修改文档但保留原始文件，需要保存为新文件。",
  "reasoning": "使用 save_as 参数指定新文件路径，原始文件保持不变。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "word_processor",
    "args": {
      "file_path": "D:\\溯源\\报告模板\\报告.docx",
      "operation": "replace",
      "find": "旧数据",
      "replace": "新数据",
      "save_as": "D:\\溯源\\报告模板\\报告_已修改.docx"
    }
  }
}
```

---

## PowerPoint 文档修改流程

### 场景 1：删除特定文本

```json
{
  "thought": "用户要求从演示文稿中删除所有'待定'字样。",
  "reasoning": "使用 search_and_replace 操作，将'待定'替换为空字符串。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "ppt_processor",
    "args": {
      "file_path": "D:\\溯源\\演示文稿.pptx",
      "operation": "search_and_replace",
      "search_text": "待定",
      "replace_text": ""
    }
  }
}
```

### 场景 2：批量替换多个文本

```json
{
  "thought": "演示文稿中有多处需要修改：'2024'改为'2025'，'Q1'改为'Q2'。",
  "reasoning": "可以使用两次 replace 操作，或者先列出所有幻灯片确认需要修改的位置。",
  "action": {
    "type": "TOOL_CALLS",
    "tool_calls": [
      {
        "tool": "ppt_processor",
        "args": {
          "file_path": "D:\\溯源\\演示文稿.pptx",
          "operation": "replace",
          "find": "2024",
          "replace": "2025"
        }
      },
      {
        "tool": "ppt_processor",
        "args": {
          "file_path": "D:\\溯源\\演示文稿.pptx",
          "operation": "replace",
          "find": "Q1",
          "replace": "Q2"
        }
      }
    ]
  }
}
```

---

## Excel 文档修改流程

### 场景 1：修改单个单元格

```json
{
  "thought": "用户要求将 A1 单元格的内容修改为'新标题'。",
  "reasoning": "使用 write_cell 操作直接修改单元格内容。",
  "action": {
    "type": "TOOL_CALL",
    "tool": "excel_processor",
    "args": {
      "file_path": "D:\\溯源\\数据.xlsx",
      "operation": "write_cell",
      "sheet_name": "Sheet1",
      "cell_address": "A1",
      "value": "新标题"
    }
  }
}
```

### 场景 2：批量修改单元格

```json
{
  "thought": "用户要求将 A1:A10 区域的所有数据都乘以2。",
  "reasoning": "先读取区域数据，处理后再写回。",
  "action": {
    "type": "TOOL_CALLS",
    "tool_calls": [
      {
        "tool": "excel_processor",
        "args": {
          "file_path": "D:\\溯源\\数据.xlsx",
          "operation": "read_range",
          "sheet_name": "Sheet1",
          "range_address": "A1:A10"
        }
      }
    ]
  }
}
```

---

## 常见错误和解决方案

### 错误 1：直接猜测文本内容

❌ **错误**：
```json
{
  "operation": "replace",
  "find": "2025年1月22日成都市臭氧8小时滑动浓度（O3_8h）为41 μg/m³",
  "replace": ""
}
```

**问题**：文档中可能是"微克/立方米"而不是"μg/m³"，或者括号类型不同。

✅ **解决方案**：
1. 先调用 `read` 操作读取文档
2. 从读取结果中复制精确的文本
3. 使用精确文本执行替换

### 错误 2：未使用 search_and_replace 处理相似表述

❌ **错误**：
```json
{
  "operation": "replace",
  "find": "臭氧浓度",
  "replace": ""
}
```

**问题**：只能匹配"臭氧浓度"，无法匹配"臭氧8小时浓度"、"臭氧滑动浓度"等。

✅ **解决方案**：
```json
{
  "operation": "search_and_replace",
  "search_text": "*臭氧*浓度*",
  "replace_text": "",
  "use_wildcards": true
}
```

### 错误 3：在 Excel 工具中寻找 search_and_replace

❌ **错误**：
```json
{
  "tool": "excel_processor",
  "operation": "search_and_replace"
}
```

**问题**：Excel 工具没有 `search_and_replace` 操作。

✅ **解决方案**：
- Excel 主要用于单元格操作，使用 `read_cell/write_cell` 或 `read_range/write_range`

### 错误 4：未考虑文档可能被锁定

❌ **错误**：
连续多次操作同一文档而不检查文件状态。

✅ **解决方案**：
- 工具内部会自动处理文档的打开和关闭
- 如果文件被其他程序占用，会返回错误信息

---

## Agent 实现建议

### 1. 在 System Prompt 中明确流程

```
## Office 文档修改流程

当用户要求修改 Office 文档时，必须遵循以下流程：

1. 【必须】先读取文档内容
   - Word: operation="read"
   - PowerPoint: operation="list_slides" 或 operation="read"
   - Excel: operation="list_sheets" 或 operation="read_range"

2. 【分析】分析文档内容，找到需要修改的精确文本

3. 【执行】选择合适的替换操作
   - 精确替换: operation="replace"
   - 模糊匹配: operation="search_and_replace"
   - 批量替换: operation="batch_replace"

4. 【验证】（可选）再次读取确认修改成功

⚠️ 重要：必须使用文档中实际存在的精确文本，包括标点符号、空格、大小写等。
```

### 2. 在工具描述中提供示例

在 `get_function_schema` 中提供详细的使用示例，帮助 LLM 理解正确的调用方式。

### 3. 返回详细的错误信息

当操作失败时，返回详细的错误信息和建议，帮助 LLM 纠正错误。

---

## 测试场景

### 测试用例 1：Word 文档删除文本

```
用户输入："删除文档中'臭氧滑动8小时最大浓度（O3_8h）为41微克/立方米'的内容"

期望流程：
1. Agent 调用 read 操作读取文档
2. Agent 从返回结果中找到精确文本
3. Agent 调用 replace 操作删除文本
4. Agent 返回成功消息
```

### 测试用例 2：Word 文档模糊匹配删除

```
用户输入："把文档中所有类似'O3_8h浓度为41微克/立方米'的表述都删除"

期望流程：
1. Agent 调用 read 操作读取文档
2. Agent 识别出需要使用 search_and_replace
3. Agent 构造通配符模式 "*O3_8h*微克/立方米*"
4. Agent 调用 search_and_replace 操作
5. Agent 返回删除了多少处匹配
```

### 测试用例 3：PPT 批量替换

```
用户输入："把演示文稿中所有的'待定'改为'已完成'"

期望流程：
1. Agent 调用 list_slides 操作查看幻灯片
2. Agent 调用 search_and_replace 或 replace 操作
3. Agent 返回修改成功
```

---

## 总结

正确的 Office 文档修改流程可以概括为：

1. **先读取** - 了解文档内容
2. **精确定位** - 找到需要修改的确切文本
3. **选择操作** - replace/search_and_replace/batch_replace
4. **执行修改** - 使用精确文本参数
5. **确认结果** - 检查返回的替换次数

遵循这个流程可以确保：
- 文档被正确修改
- 避免误删或改错内容
- 提供准确的操作反馈
