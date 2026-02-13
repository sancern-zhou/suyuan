# Office工具insert操作增强 - 支持表格/图片定位

## 修改时间
2026-02-09

## 修改目的
增强insert操作，支持在文档中的表格和图片前后插入文字分析内容，解决无法精确定位表格/图片位置的问题。

**新增功能**（2026-02-09）：
- 插入文本默认应用段落格式：两端对齐，首行缩进2字符
- 自动为所有插入的文本内容设置标准格式，保持文档风格统一

## 修改的文件

### 1. `backend/app/tools/office/word_win32_tool.py`

**新增参数**：
- `target_type`: 目标类型，可选值 "text"(默认) / "table" / "image"
- `target_index`: 目标索引（从0开始，target_type="table"或"image"时必需）

**功能实现**：

1. **position="after/before" + target_type="text"**（原有功能）
   ```python
   # 在目标文本之后插入
   {"operation": "insert", "position": "after", "target": "目标文本", "content": "内容"}
   ```

2. **position="after/before" + target_type="table"**（新增）
   ```python
   # 在第1个表格（索引0）之前插入标题
   {"operation": "insert", "position": "before",
    "target_type": "table", "target_index": 0,
    "content": "表1 污染物浓度分析"}

   # 在第1个表格之后插入分析
   {"operation": "insert", "position": "after",
    "target_type": "table", "target_index": 0,
    "content": "如表1所示，PM2.5浓度..."}
   ```

3. **position="after/before" + target_type="image"**（新增）
   ```python
   # 在第1个图片（索引0）之前插入图注
   {"operation": "insert", "position": "before",
    "target_type": "image", "target_index": 0,
    "content": "图1 轨迹分析图"}
   ```

**技术实现**：
- 表格定位：`doc.Tables(target_index + 1)` + `table.Range.Start/End - 1` 定位到表格外
- 图片定位：`doc.InlineShapes(target_index + 1)` + `shape.Range.Start/End - 1` 定位到图片外
- **重要**：不在表格/图片范围内插入，而是在表格/图片前后的正文中插入
- 错误处理：索引越界会返回明确的错误信息

**段落格式设置**（2026-02-09）：
- 所有插入的文本自动应用默认段落格式
- **两端对齐**：`ParagraphFormat.Alignment = 3` (wdAlignParagraphJustify)
- **首行缩进2字符**：`ParagraphFormat.CharacterUnitFirstLineIndent = 2`
- Word VBA 对齐常量：0=左对齐, 1=居中, 2=右对齐, 3=两端对齐, 4=分散对齐
- 使用 `_apply_paragraph_format(inserted_range)` 辅助方法统一应用格式
- 格式设置失败不影响插入操作的成功（仅记录警告日志）

**Bug修复**（2026-02-09）：
- **问题**：使用 `table.Range.InsertBefore/After()` 会在表格范围内插入，导致内容出现在表格单元格内
- **修复**：
  - `position="before"`：使用 `table.Range.Start - 1` 定位到表格之前，插入 `\n + content`
  - `position="after"`：使用 `table.Range.End` 定位到表格结束位置，插入 `\n + content`
  - 同样修复了 `target_type="image"` 的问题

### 2. `backend/app/tools/office/word_tool.py`

**更新函数签名**：
```python
async def execute(
    self,
    ...
    target_type: str = "text",  # 新增
    target_index: int = None,    # 新增
    **kwargs
)
```

**Bug修复**（2026-02-09）：
- **问题**：`target_type` 和 `target_index` 参数虽然定义在函数签名中，但在 `insert_kwargs` 中使用 `kwargs.get()` 获取，导致参数传递失败
- **原因**：命名参数不会出现在 `kwargs` 字典中，必须直接使用参数变量
- **修复**：
  ```python
  # 修复前（错误）
  insert_kwargs = {
      "target_type": kwargs.get("target_type", "text"),  # ❌ 永远获取不到
      "target_index": kwargs.get("target_index")         # ❌ 永远获取不到
  }

  # 修复后（正确）
  insert_kwargs = {
      "target_type": target_type,   # ✅ 直接使用参数变量
      "target_index": target_index  # ✅ 直接使用参数变量
  }
  ```

**更新Schema**：
```python
"target_type": {
    "type": "string",
    "enum": ["text", "table", "image"],
    "description": "目标类型（用于 insert 操作的 position=after/before）"
},
"target_index": {
    "type": "integer",
    "description": "目标索引（从0开始，用于 insert 操作且 target_type=table/image 时）"
}
```

### 3. `backend/app/agent/tool_adapter.py`

**更新工具摘要**：
```
• insert: 插入文本（支持在表格/图片前后插入）
  必填: path, operation, content, position
  可选: target(target_type=text时), target_type(text/table/image), target_index(表格/图片索引)
  position: end(末尾)/start(开头)/after(目标后)/before(目标前)
  target_type: text(默认)/table(定位表格)/image(定位图片)
  示例1(末尾): {"position": "end", "content": "追加内容"}
  示例2(表格前): {"position": "before", "target_type": "table", "target_index": 0, "content": "表1标题"}
  示例3(表格后): {"position": "after", "target_type": "table", "target_index": 0, "content": "分析"}
```

**更新最佳实践**：
1. 定位表格/图片前先用tables操作查看文档结构
2. 使用target_type="table"/"image"+target_index精确定位
3. 文本目标需精确匹配，建议先read查看文档
4. 对已存在的文档，优先使用索引定位

## 使用场景

### 场景1：为表格添加标题和分析

```python
# Step 1: 查看表格结构
{"operation": "tables", "path": "D:\\docs.docx"}
# 返回：2个表格，表格1是污染物数据

# Step 2: 在表格1前插入标题
{"operation": "insert",
 "position": "before",
 "target_type": "table",
 "target_index": 0,
 "content": "表1 2025年1月污染物浓度统计"}

# Step 3: 在表格1后插入分析
{"operation": "insert",
 "position": "after",
 "target_type": "table",
 "target_index": 0,
 "content": "如表1所示，PM2.5平均浓度为35μg/m³，O3浓度为56μg/m³..."}
```

### 场景2：为图片添加图注

```python
# Step 1: 查看文档了解图片数量（通过read或其他方式）

# Step 2: 在第1张图片前插入图注
{"operation": "insert",
 "position": "before",
 "target_type": "image",
 "target_index": 0,
 "content": "图1 后向轨迹分析图"}
```

## 向后兼容性

- ✅ 完全向后兼容：不指定target_type时默认为"text"，保持原有行为
- ✅ 原有用法不受影响：使用target参数的文本定位方式继续有效
- ✅ 新功能独立：新增的target_type和target_index只在需要时使用

## 优势

1. **精确定位**：通过索引直接定位表格/图片，无需文本匹配
2. **无需模板**：不需要预先在文档中预留占位符
3. **适用已存在文档**：可以直接操作已有的Word文档
4. **错误清晰**：索引越界时会返回明确的错误信息

### 4. `backend/app/agent/core/loop.py`

**修改内容**：修复Office工具完整数据传递问题

**问题描述**：
- Office工具（Word/Excel/PPT）返回完整数据，但LLM只接收到摘要
- 原因：`add_assistant_message(observation["summary"])` 只传递摘要到conversation_history
- conversation_history优先级高于working_memory，导致完整数据无法被LLM访问

**解决方案**（方案B）：
- 使用 `_format_observation(observation)` 完整格式化内容替代摘要
- 该方法已支持Office工具完整数据展示（第1575-1620行）

**附加修复**（2026-02-09）：
- 修复 `_format_observation` 方法对 `tables` 操作的处理
- 新增对 `data.tables` 字段的完整展示支持
- 现在支持以下Office数据格式：
  - `data.content` - 文档内容
  - `data.tables` - 表格数据（完整显示每个表格的二维数组）
  - `data.data` - Excel数据（二维数组）
  - `data.stats` - 统计信息
  - `data.range` - 读取范围信息

### 5. `backend/app/agent/context/simplified_context_builder.py`

**修复内容**：避免重复显示观察结果

**问题描述**：
- `conversation_history` 已包含完整的助手回复（包括完整数据）
- `latest_observation` 又是同一个观察结果
- 导致表格等数据在上下文中重复显示两次

**解决方案**：
- 仅当 `conversation_history` 为空时才添加 `latest_observation`
- 避免数据重复，节省token

**修改前**：
```python
# 3. 最新观察结果
if latest_observation:
    sections.append(f"## 最新观察结果\n{latest_observation}")
```

**修改后**：
```python
# 3. 最新观察结果（仅当conversation_history为空时添加，避免重复）
# conversation_history已包含所有历史对话，包括完整的observation数据
# latest_observation通常已经包含在conversation_history的最后一条助手消息中
if latest_observation and not conversation_history:
    sections.append(f"## 最新观察结果\n{latest_observation}")
```

**修改位置**：
- 第665行（multi_step模式）
- 第1430行（single_step模式）

**修改前**：
```python
if observation.get("summary"):
    self.memory.session.add_assistant_message(observation["summary"])
```

**修改后**：
```python
if observation.get("summary"):
    # 使用完整格式化内容（包含完整数据）而非仅摘要
    full_message = self._format_observation(observation)
    self.memory.session.add_assistant_message(full_message)
```

**影响范围**：
- 所有工具的完整数据都会传递给LLM（包括Office工具、bash命令等）
- `_format_observation` 方法已智能处理：
  - Office工具：显示完整文档内容、统计数据、分页信息
  - Bash命令：显示完整stdout/stderr、退出码
  - 其他工具：显示data字段内容

## 版本信息
- 版本号: 2.4.0 → 2.5.0
- 修改日期: 2026-02-09
