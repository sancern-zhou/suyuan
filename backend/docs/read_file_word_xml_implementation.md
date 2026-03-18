# ReadFile 工具 - Word XML 智能分层实现总结

## 实现概述

为 `read_file` 工具添加了 **"智能分层"策略**，用于处理 Word XML 文件（`document.xml`）。

**核心理念**：
- **LLM 明确控制**：通过参数（`raw_mode`、`include_formatting`）表达意图
- **系统智能适配**：根据文件大小自动选择合理的默认模式
- **简单优先**：避免复杂的关键词检测，保持可预测性

## 三种读取模式

| 模式 | 用途 | Token 消耗 | 格式保留 | 触发条件 |
|------|------|------------|----------|----------|
| **text** | 纯文本提取 | 最低 (~10% 原始) | 无 | 大文件（≥100KB） |
| **structured** | 结构化摘要 | 低 (~20% 原始) | 部分（标题、表格） | 小文件（<100KB） |
| **raw** | 完整原始 XML | 高 (100%) | 完整 | `raw_mode=True` |

## 核心代码结构

### 1. 文件类型检测

```python
def _is_word_xml(self, file_path: Path) -> bool:
    """检测是否是 Word XML 文件（document.xml）

    检查条件：
    1. 文件名是 document.xml
    2. 位于 word 目录下
    3. 存在 _rels 目录（Office 文档特征）
    4. 文件内容包含 w:document 或 openxmlformats 命名空间
    """
```

### 2. 智能模式选择

```python
async def _read_word_xml(self, file_path, file_size, raw_mode=False,
                          include_formatting=False, max_paragraphs=None):
    """Word XML 智能分层读取主方法

    决策逻辑：
    1. raw_mode=True → 返回完整原始 XML
    2. include_formatting=True → 返回结构化内容
    3. 文件大小 < 100KB → structured 模式
    4. 文件大小 ≥ 100KB → text 模式
    """
```

### 3. 三种模式实现

#### Text 模式（纯文本提取）

```python
async def _extract_text_from_word_xml(self, file_path, file_size, max_paragraphs):
    """提取纯文本（最节省 tokens）

    使用 LobsterAI 的递归文本提取方式：
    - 只提取 <w:t> 标签内的文本
    - 跳过空白节点
    - 压缩率：~90%

    返回格式：
    {
        "mode": "text",
        "content": "纯文本内容",
        "compression_ratio": "90.0%"
    }
    """
```

#### Structured 模式（结构化摘要）

```python
async def _extract_structured_from_word_xml(self, file_path, file_size, max_paragraphs):
    """提取结构化内容（保留标题、表格等）

    保留关键结构：
    - 标题层级（转换为 Markdown # ## ###）
    - 表格结构（转换为 Markdown 表格）
    - 段落文本
    - 图片引用（[图片引用: rIdX]）

    压缩率：~80%

    返回格式：
    {
        "mode": "structured",
        "content": "# 标题1\n\n段落文本\n\n## 标题2\n...",
        "compression_ratio": "80.0%"
    }
    """
```

#### Raw 模式（原始 XML）

```python
async def _read_raw_word_xml(self, file_path, file_size):
    """读取完整原始 XML（用于精确编辑）

    返回格式：
    {
        "mode": "raw",
        "content": "<?xml version...<w:document>...</w:document>",
        "size": 原始大小
    }
    """
```

## LLM 使用场景

### 场景 1：快速阅读（默认模式）

```
用户：查看这个文档的内容

系统行为：
→ 调用 read_file("document.xml")
→ 检测文件大小 80KB（<100KB）
→ 自动使用 structured 模式
→ 返回结构化摘要（节省 ~80% tokens）
```

### 场景 2：大文档阅读（自动优化）

```
用户：这个文档很长，帮我看看主要内容

系统行为：
→ 调用 read_file("document.xml")
→ 检测文件大小 150KB（≥100KB）
→ 自动使用 text 模式
→ 返回纯文本（节省 ~90% tokens）
```

### 场景 3：精确编辑（LLM 指定参数）

```
用户：我需要编辑标题样式，读取完整 XML

LLM 调用：
→ read_file("document.xml", raw_mode=True)
→ 系统返回完整原始 XML
→ LLM 使用 edit_file 修改
→ 最后使用 pack_office 重新打包
```

### 场景 4：控制读取量（LLM 指定参数）

```
用户：只读取前 50 个段落看看内容

LLM 调用：
→ read_file("document.xml", max_paragraphs=50)
→ 系统只读取前 50 个段落
→ 进一步节省 tokens
```

## 工具描述（Function Calling Schema）

```json
{
  "name": "read_file",
  "description": "读取文件内容（统一文件读取入口，智能识别类型并自动优化）\n\nWord XML 智能分层：\n系统会根据文件大小和任务自动选择最优模式：\n• 小文档（<100KB）：自动使用 structured 模式（保留结构）\n• 大文档（≥100KB）：自动使用 text 模式（节省 tokens）\n• 需要编辑格式：在任务中提到'编辑'、'修改'等关键词时自动使用 raw 模式\n\n高级参数（通常不需要手动指定）：\n• raw_mode=True：强制返回完整原始 XML（用于精确编辑）\n• include_formatting=True：保留格式信息（structured 模式的增强版）\n• max_paragraphs=50：限制读取段落数（进一步节省 tokens）",
  "parameters": {
    "path": "文件路径",
    "raw_mode": "是否返回原始内容（Word XML 专用，默认 False）",
    "include_formatting": "是否保留格式信息（Word XML 专用，默认 False）",
    "max_paragraphs": "最大段落数（Word XML 专用，默认不限制）"
  }
}
```

## 关键优势

### 1. LLM 明确控制
- ✅ LLM 通过参数明确表达意图（`raw_mode=True` 需要编辑）
- ✅ 不依赖关键词检测，避免误判
- ✅ 行为可预测、可解释

### 2. 系统智能适配
- ✅ 基于文件大小的简单规则（无需复杂推断）
- ✅ 小文档保留结构，大文档节省 tokens
- ✅ 默认行为合理，减少手动调参

### 3. Token 高效
- ✅ 小文档：structured 模式（~80% 压缩）
- ✅ 大文档：text 模式（~90% 压缩）
- ✅ 可进一步限制段落数

### 4. 保持灵活性
- ✅ 参数覆盖机制（`raw_mode=True`）
- ✅ 向后兼容（不影响其他文件类型）
- ✅ 精确编辑能力完整保留

## 与参考项目对比

| 维度 | LobsterAI | Claude Code | 本实现 |
|------|-----------|-------------|--------|
| 控制方式 | 工作流树（提示词） | 自动检测 | 智能推断 |
| Token 优化 | 手动选择模式 | 自动分析 | 自动选择模式 |
| LLM 自由度 | 低（需遵循规则） | 高 | 高 |
| 灵活性 | 中 | 中 | 高 |
| 适用场景 | 复杂工作流 | 简单读取 | 通用场景 |

## 测试验证

运行测试脚本：
```bash
cd backend
python test_read_file_word_xml.py
```

测试覆盖：
- ✅ Word XML 文件检测
- ✅ 三种读取模式（text/structured/raw）
- ✅ 自动模式选择（基于文件大小）
- ✅ 参数覆盖（raw_mode, max_paragraphs）

## 依赖要求

```bash
pip install defusedxml
```

## 文件修改清单

1. **app/tools/utility/read_file_tool.py**
   - 添加 `_is_word_xml()` 方法
   - 添加 `_read_word_xml()` 方法
   - 添加 `_extract_text_from_word_xml()` 方法
   - 添加 `_extract_structured_from_word_xml()` 方法
   - 添加 `_read_raw_word_xml()` 方法
   - 添加 `_get_paragraph_text()` 辅助方法
   - 添加 `_extract_table_text()` 辅助方法
   - 更新 `execute()` 方法签名
   - 更新工具描述和版本号（v2.0.0）

2. **test_read_file_word_xml.py**（新增）
   - 完整的测试套件

## 设计原则

### 避免的设计（已移除）
- ❌ **关键词检测**：不使用"编辑"、"修改"等关键词推断意图
  - 原因：容易误判，不够可靠
  - 替代：让 LLM 通过参数明确表达

### 采用的设计
- ✅ **简单规则**：基于文件大小的明确阈值（100KB）
- ✅ **LLM 控制**：通过参数（`raw_mode`）覆盖默认行为
- ✅ **可预测性**：行为清晰，易于理解和调试

## 后续优化方向

### 短期（已完成）
- ✅ 基于文件大小的自动模式选择
- ✅ 参数覆盖机制
- ✅ 三种模式完整实现

### 中期（可选）
- 🔲 支持更多文件类型（Excel、PowerPoint XML）
- 🔲 智能采样策略（超大文件分段读取）
- 🔲 根据实际使用情况调整阈值

### 长期（可选）
- 🔲 支持 .docx 文件直接读取（无需解包）
- 🔲 学习 LLM 的参数使用偏好
- 🔲 动态调整文件大小阈值

## 使用示例

### 示例 1：默认使用（推荐）

```python
# LLM 只需调用
result = await read_file("unpacked_doc/word/document.xml")

# 系统自动：
# 1. 检测到 Word XML 文件
# 2. 检查文件大小
# 3. 选择最优模式
# 4. 返回优化后的内容
```

### 示例 2：精确编辑

```python
# LLM 需要编辑格式
result = await read_file(
    "unpacked_doc/word/document.xml",
    raw_mode=True  # 强制返回完整 XML
)

# 然后使用 edit_file 修改
# 最后使用 pack_office 重新打包
```

### 示例 3：控制读取量

```python
# LLM 只需要概览
result = await read_file(
    "unpacked_doc/word/document.xml",
    max_paragraphs=50  # 只读取前 50 个段落
)
```

## 总结

本实现完全符合 **"LLM 完全自由 + 系统智能适配"** 的设计理念：

- **LLM 完全自由**：通过自然语言表达意图，无需理解技术细节
- **系统智能适配**：自动检测文件类型、大小，选择最优读取模式
- **向后兼容**：不影响现有功能，平滑升级
- **可扩展性**：预留参数覆盖机制，支持高级场景
