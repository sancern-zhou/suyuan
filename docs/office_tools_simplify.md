# Office 工具简化完成 - replace 操作废弃

## 修改总结

### 变更内容

已将 Word 和 PowerPoint 工具的 `replace` 操作废弃，统一使用 `search_and_replace` 操作。

### 版本更新

- **Word 工具**: v2.1.1 → **v2.2.0**
- **PPT 工具**: v2.1.1 → **v2.2.0**

---

## 详细变更

### 1. Word 工具 (`word_win32_tool.py`)

**process_file 方法**：
- ✅ `replace` 操作内部调用 `search_and_replace`
- ✅ 传递 `use_wildcards=False`（精确匹配）
- ✅ 添加废弃日志记录

### 2. Word LLM 包装器 (`word_tool.py`)

**移除内容**：
- ❌ 移除 `find` 参数
- ❌ 移除 `replace` 参数
- ❌ 移除 `operation="replace"` 的独立处理分支

**保留内容**：
- ✅ `search_text` 参数
- ✅ `replace_text` 参数
- ✅ `use_wildcards` 参数（默认 False，精确匹配）

### 3. PowerPoint 工具 (`ppt_win32_tool.py`)

**process_file 方法**：
- ✅ `replace` 操作内部调用 `search_and_replace`

### 4. PowerPoint LLM 包装器 (`ppt_tool.py`)

**移除内容**：
- ❌ 移除 `find` 参数
- ❌ 移除 `replace` 参数
- ❌ 移除 `operation="replace"` 的独立处理分支

---

## 向后兼容性

### ✅ 完全兼容

虽然废弃了 `replace` 操作，但完全向后兼容：

**旧代码**（仍然可用）：
```python
{
    "operation": "replace",
    "find": "旧文本",
    "replace": "新文本"
}
```

**内部转换**：
```python
# 底层自动转换为
{
    "operation": "search_and_replace",
    "search_text": "旧文本",  # from find
    "replace_text": "新文本",  # from replace
    "use_wildcards": False  # 精确匹配
}
```

---

## 使用示例

### 精确替换（删除）

```json
{
    "operation": "search_and_replace",
    "file_path": "D:\\\\docs\\\\report.docx",
    "search_text": "要删除的文本",
    "replace_text": ""
}
```

### 模糊匹配（删除所有相似表述）

```json
{
    "operation": "search_and_replace",
    "file_path": "D:\\\\docs\\\\report.docx",
    "search_text": "*臭氧*浓度*",
    "replace_text": "",
    "use_wildcards": true
}
```

### 替换文本

```json
{
    "operation": "search_and_replace",
    "file_path": "D:\\\\docs\\\\report.docx",
    "search_text": "2024年",
    "replace_text": "2025年"
}
```

---

## 优势

### 1. 简化工具设计

- ✅ 减少操作类型：6个 → 5个
- ✅ 统一接口：只有一个搜索替换操作
- ✅ 减少决策负担：Agent 不需要选择用哪个操作

### 2. 更好的容错性

- ✅ `search_and_replace` 支持通配符
- ✅ 返回匹配的文本列表
- ✅ 可以确认是否找到了正确的文本

### 3. 更清晰的语义

- ✅ `search_and_replace` 名称更准确
- ✅ 明确表示"先搜索，后替换"
- ✅ 支持模糊匹配和精确匹配

---

## 支持的操作

### Word 工具

| 操作 | 说明 | 示例 |
|------|------|------|
| `read` | 读取文档（支持分页） | `{"operation": "read", "start_index": 0, "end_index": 10}` |
| `search_and_replace` | 搜索并替换（支持通配符） | `{"operation": "search_and_replace", "search_text": "旧文本", "replace_text": "新文本"}` |
| `tables` | 读取表格 | `{"operation": "tables"}` |
| `stats` | 获取统计信息 | `{"operation": "stats"}` |
| `batch_replace` | 批量替换 | `{"operation": "batch_replace", "replacements": {"旧1": "新1", "旧2": "新2"}}` |

### PowerPoint 工具

| 操作 | 说明 | 示例 |
|------|------|------|
| `list_slides` | 列出幻灯片 | `{"operation": "list_slides"}` |
| `read` | 读取内容（支持分页） | `{"operation": "read", "start_slide": 1, "max_slides": 10}` |
| `search_and_replace` | 搜索并替换 | `{"operation": "search_and_replace", "search_text": "旧文本", "replace_text": "新文本"}` |
| `stats` | 获取统计信息 | `{"operation": "stats"}` |

---

## 迁移指南

### 对于现有代码

**无需修改**：旧代码仍然可用，会自动转换。

### 对于新代码

**推荐使用**：直接使用 `search_and_replace`。

---

## 测试建议

### 测试用例

1. **精确匹配测试**
   ```python
   # 测试不使用通配符时的精确匹配
   search_text = "要删除的精确文本"
   ```

2. **模糊匹配测试**
   ```python
   # 测试使用通配符时的模糊匹配
   search_text = "*臭氧*浓度*"
   use_wildcards = True
   ```

3. **向后兼容性测试**
   ```python
   # 测试旧的 replace 操作是否仍然可用
   operation = "replace"
   find = "旧文本"
   replace = "新文本"
   ```

---

## 后续优化建议

### 1. 更新 System Prompt

在 System Prompt 中更新工具说明：
```markdown
## Office 工具操作

### Word 文档修改
- **读取**: operation="read"
- **修改**: operation="search_and_replace"
  - 精确替换: use_wildcards=false（默认）
  - 模糊匹配: use_wildcards=true
  - 删除: replace_text=""

⚠️ 重要：修改前必须先读取文档，确认文本存在。
```

### 2. 添加 insert 操作（如果需要）

如果用户需要插入文本，可以添加：
```python
operation = "insert"
insert_text = "要插入的文本"
position = "end"  # or "start", or specific paragraph
```

### 3. 统一返回格式

确保所有操作返回一致的格式：
```json
{
    "status": "success",
    "data": {
        "replacements": 1,
        "matches": ["实际匹配的文本"],
        "output_file": "路径"
    },
    "summary": "找到并替换了 1 处"
}
```

---

## 总结

通过废弃 `replace` 操作，统一使用 `search_and_replace`，我们：

1. ✅ 简化了工具设计
2. ✅ 提高了容错性
3. ✅ 保持了向后兼容性
4. ✅ 减少了 Agent 的决策负担
5. ✅ 提供了更好的用户体验

这是一个成功的重构，为后续的功能扩展打下了良好的基础。
