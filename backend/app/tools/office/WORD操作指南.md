# WORD 文档操作指南

## 概述

本指南介绍 Word 文档（.docx）的读取、编辑和处理方法。系统提供两种编辑方式：
- **简单编辑**：使用 `find_replace_word` 工具
- **复杂编辑**：使用 `word_edit` 工具（推荐）

---

## 核心原则

### 1. 工具选择优先级

| 任务类型 | 推荐工具 | 理由 |
|---------|---------|------|
| 简单文本替换 | `find_replace_word` | 快速、直接 |
| 接受/拒绝修订 | `accept_word_changes` | 专门处理修订 |
| 复杂结构编辑 | `word_edit` | 强大、灵活 |
| 读取文档内容 | `read_docx` | 获取完整内容 |

### 2. 编辑前必须阅读

在使用任何 Word 编辑工具之前，**必须**先执行：
```python
# 第一步：读取文档
read_docx(path="文档.docx")

# 第二步：根据读取结果选择合适的编辑工具
```

---

## 工具详解

### 1. read_docx - 读取 Word 文档

**功能**：读取 .docx 文件的完整内容（文本、段落、样式）

**用法**：
```python
read_docx(
    path="文档.docx",
    max_paragraphs=100  # 可选：限制段落数
)
```

**返回结果**：
```json
{
  "success": true,
  "data": {
    "paragraphs": [...],    // 段落列表
    "styles": {...},        // 样式信息
    "metadata": {...}       // 文档元数据
  },
  "summary": "共 50 个段落"
}
```

---

### 2. find_replace_word - 简单文本替换

**适用场景**：
- ✅ 全局文本替换（如"2025" → "2026"）
- ✅ 简单的查找替换操作
- ❌ 不适合复杂结构编辑

**用法**：
```python
find_replace_word(
    path="文档.docx",
    find="旧文本",
    replace="新文本",
    match_case=False  # 可选：区分大小写
)
```

**示例**：
```python
# 替换所有年份
find_replace_word(
    path="年度报告.docx",
    find="2025年",
    replace="2026年"
)
```

---

### 3. word_edit - 复杂结构编辑

**适用场景**：
- ✅ 插入新段落/章节
- ✅ 删除特定内容
- ✅ 精确替换（带上下文）
- ✅ 重新组织文档结构
- ✅ 保留复杂格式

**操作类型**：

#### replace - 替换段落
```python
word_edit(
    path="文档.docx",
    operations=[
        {
            "type": "replace",
            "target": "要替换的文本",
            "replacement": "新内容",
            "context": "前后文关键词"  # 可选：提高精确度
        }
    ]
)
```

#### insert - 插入内容
```python
word_edit(
    path="文档.docx",
    operations=[
        {
            "type": "insert",
            "position": "after",  # before | after
            "target": "插入位置标记",
            "content": "要插入的新段落"
        }
    ]
)
```

#### delete - 删除内容
```python
word_edit(
    path="文档.docx",
    operations=[
        {
            "type": "delete",
            "target": "要删除的文本"
        }
    ]
)
```

---

### 4. accept_word_changes - 处理修订

**功能**：接受或拒绝 Word 文档中的修订

**用法**：
```python
accept_word_changes(
    path="有修订的文档.docx",
    action="accept"  # accept | reject
)
```

**返回结果**：
```json
{
  "success": true,
  "data": {
    "accepted_count": 15,
    "rejected_count": 0
  },
  "summary": "已接受 15 处修订"
}
```

---

## 标准操作流程

### 场景 1：简单文本替换

```python
# 1. 读取文档（了解内容）
read_docx(path="报告.docx")

# 2. 执行替换
find_replace_word(
    path="报告.docx",
    find="旧公司名称",
    replace="新公司名称"
)
```

---

### 场景 2：复杂结构编辑

```python
# 1. 读取文档（了解结构）
read_docx(path="报告.docx")

# 2. 执行复杂编辑
word_edit(
    path="报告.docx",
    operations=[
        {
            "type": "replace",
            "target": "第一章 引言",
            "replacement": "第一章 项目背景"
        },
        {
            "type": "insert",
            "position": "after",
            "target": "第一章 项目背景",
            "content": "本章介绍项目的背景和目标..."
        },
        {
            "type": "delete",
            "target": "待删除的临时内容"
        }
    ]
)
```

---

### 场景 3：处理修订

```python
# 1. 读取文档（检查修订）
read_docx(path="草稿.docx")

# 2. 接受所有修订
accept_word_changes(
    path="草稿.docx",
    action="accept"
)
```

---

## 常见错误及解决

### 错误 1：工具选择不当

❌ **错误**：用 `find_replace_word` 处理复杂编辑
```python
# 这样做会失败或结果不准确
find_replace_word(
    path="文档.docx",
    find="第一章",
    replace="第一章（更新版）"
)
```

✅ **正确**：使用 `word_edit`
```python
word_edit(
    path="文档.docx",
    operations=[{
        "type": "replace",
        "target": "第一章",
        "replacement": "第一章（更新版）"
    }]
)
```

---

### 错误 2：未读取文档直接编辑

❌ **错误**：直接编辑未读过的文档
```python
# 不知道文档结构就编辑，容易出错
word_edit(path="未知文档.docx", ...)
```

✅ **正确**：先读取再编辑
```python
# 第一步：了解文档内容
read_docx(path="未知文档.docx")

# 第二步：根据内容设计编辑操作
word_edit(path="未知文档.docx", ...)
```

---

### 错误 3：替换文本不精确

❌ **错误**：替换短文本导致误替换
```python
# 这样会替换所有"报告"二字
find_replace_word(
    path="文档.docx",
    find="报告",
    replace="年度报告"
)
```

✅ **正确**：使用上下文提高精确度
```python
word_edit(
    path="文档.docx",
    operations=[{
        "type": "replace",
        "target": "报告",
        "context": "本",
        "replacement": "年度报告"
    }]
)
```

---

## 最佳实践

### 1. 编辑前检查清单

- [ ] 是否已读取文档了解内容？
- [ ] 是否选择了正确的工具？
- [ ] 替换文本是否足够精确？
- [ ] 是否需要保留原始格式？

### 2. 批量操作建议

对于多文档批量操作，使用 Python 脚本：
```python
from pathlib import Path

for file in Path("reports/").glob("*.docx"):
    find_replace_word(
        path=str(file),
        find="2025年",
        replace="2026年"
    )
```

### 3. 错误处理

编辑失败时，检查：
1. 文件路径是否正确
2. 文件是否被其他程序占用
3. 操作类型是否支持
4. 目标文本是否存在

---

## 相关资源

- [python-docx 文档](https://python-docx.readthedocs.io/)
- Word Open XML 规范
- Anthropic Word Skill: https://github.com/anthropics/skills/tree/main/skills/word
