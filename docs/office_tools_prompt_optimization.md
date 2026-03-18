# Office 工具提示词优化总结

## 问题分析

### 原始错误
```
TypeError: ReadFileTool.execute() missing 1 required positional argument: 'path'
```

### 根本原因
1. LLM 尝试使用 `read_file` 直接读取 `.docx` 文件
2. `.docx` 是二进制格式（ZIP 压缩的 XML），不是纯文本
3. `read_file` 工具无法处理二进制格式，返回"文本编码错误"

## 优化方案

### 1. 添加文件类型识别指导

在"工作原则"部分添加：

```markdown
1. **文件类型识别**：根据文件扩展名选择正确的工具
   - `.txt`, `.md`, `.json`, `.xml`, `.py`, `.js` 等文本文件 → 使用 `read_file`
   - `.docx`, `.xlsx`, `.pptx` 等 Office 文件 → 使用 Office 工具（不能用 `read_file`）
   - `.png`, `.jpg`, `.jpeg` 等图片文件 → 使用 `read_file`（自动分析）
   - `.pdf` 文件 → 使用 `read_file`（支持指定页面）

2. **Office 文件处理流程**：
   - Word 文档 (`.docx`) → 先 `unpack_office` 解包，再 `read_file` 读取 XML
   - Excel 表格 (`.xlsx`) → 先 `unpack_office` 解包，再 `read_file` 读取 XML
   - PPT 演示 (`.pptx`) → 先 `unpack_office` 解包，再 `read_file` 读取 XML
```

### 2. 添加醒目的错误提示

在"Office 文件操作指南"开头添加：

```markdown
### ⚠️ 关键提示

**Office 文件不能直接用 `read_file` 读取！**

- ❌ **错误示例**：`read_file(path="report.docx")` → 会报错"文本编码错误"
- ✅ **正确方法**：
  1. 先解包：`unpack_office(file_path="report.docx", output_dir="unpacked/")`
  2. 再读取：`read_file(path="unpacked/word/document.xml")`

**原因**：`.docx/.xlsx/.pptx` 是压缩的 XML 文件（ZIP 格式），不是纯文本文件
```

### 3. 添加错误处理指导

在"Office 操作最佳实践"中添加：

```markdown
**3. 常见错误处理**
- 如果 `read_file` 返回"文本编码错误"且文件是 `.docx/.xlsx/.pptx`：
  → 说明文件是 Office 格式，需要先解包
  → 使用 `unpack_office` 解包后再读取 XML 文件
```

## 优化效果

### 优化前
- LLM 不知道 Office 文件需要特殊处理
- 直接使用 `read_file` 读取 `.docx` 文件
- 导致"文本编码错误"

### 优化后
- LLM 能够识别文件类型
- 自动选择正确的工具链
- 正确的处理流程：`unpack_office` → `read_file` → `edit_file` → `pack_office`

## 完整的 Office 文件处理流程

### 场景 1：读取 Word 文档内容

```json
// 步骤 1：解包
{
  "tool": "unpack_office",
  "args": {
    "file_path": "report.docx",
    "output_dir": "unpacked/"
  }
}

// 步骤 2：读取 XML
{
  "tool": "read_file",
  "args": {
    "path": "unpacked/word/document.xml"
  }
}
```

### 场景 2：编辑 Word 文档

```json
// 步骤 1：解包
{
  "tool": "unpack_office",
  "args": {
    "file_path": "report.docx",
    "output_dir": "unpacked/"
  }
}

// 步骤 2：读取 XML
{
  "tool": "read_file",
  "args": {
    "path": "unpacked/word/document.xml"
  }
}

// 步骤 3：编辑 XML
{
  "tool": "edit_file",
  "args": {
    "file_path": "unpacked/word/document.xml",
    "old_string": "旧内容",
    "new_string": "新内容"
  }
}

// 步骤 4：重新打包
{
  "tool": "pack_office",
  "args": {
    "input_dir": "unpacked/",
    "output_file": "report_edited.docx"
  }
}
```

### 场景 3：使用高级工具（推荐）

对于常见操作，直接使用高级工具：

```json
// Word 查找替换
{
  "tool": "find_replace_word",
  "args": {
    "file_path": "report.docx",
    "find_text": "旧术语",
    "replace_text": "新术语"
  }
}

// Excel 公式重算
{
  "tool": "recalc_excel",
  "args": {
    "file_path": "data.xlsx"
  }
}

// Word 接受修订
{
  "tool": "accept_word_changes",
  "args": {
    "input_file": "draft.docx",
    "output_file": "final.docx"
  }
}
```

## 提示词优化位置

**文件**：`backend/app/agent/prompts/assistant_prompt.py`

**优化内容**：
1. 工作原则 - 添加文件类型识别
2. Office 文件操作指南 - 添加关键提示
3. Office 操作最佳实践 - 添加错误处理

## 预期效果

### 用户请求
"读取 D:/溯源/报告模板/2025年7月1日臭氧垂直.docx"

### LLM 行为（优化后）

**步骤 1：识别文件类型**
- 文件扩展名：`.docx`
- 判断：这是 Office 文件，不能直接用 `read_file`

**步骤 2：选择正确工具**
- 使用 `unpack_office` 解包

**步骤 3：读取内容**
- 使用 `read_file` 读取 `unpacked/word/document.xml`

**步骤 4：返回结果**
- 向用户展示文档内容

## 总结

通过提示词优化，LLM 现在能够：
1. ✅ 正确识别 Office 文件类型
2. ✅ 选择合适的工具链
3. ✅ 避免"文本编码错误"
4. ✅ 提供完整的 Office 文件处理能力

---

**优化完成日期**：2026-02-20
**优化文件**：`backend/app/agent/prompts/assistant_prompt.py`
