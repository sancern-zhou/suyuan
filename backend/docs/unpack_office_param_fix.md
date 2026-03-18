# unpack_office 工具参数统一修复

**日期**: 2026-02-22
**问题**: 工具参数名与其他文件操作工具不一致，导致调用失败

---

## ✅ 修复内容

### 问题
LLM 调用时传入 `{"path": "..."}` 参数，但工具定义的参数名是 `file_path`，导致 TypeError。

### 解决方案
统一工具参数格式，与 `read_file` 等其他文件操作工具保持一致：

### 修改详情

**文件**: `app/tools/office/unpack_tool.py`

#### 1. 参数重命名
```python
# ❌ 旧参数
async def execute(
    self,
    file_path: str,  # 与其他工具不一致
    output_dir: str,
    **kwargs
)

# ✅ 新参数
async def execute(
    self,
    path: str,  # 与 read_file 一致
    output_dir: Optional[str] = None,  # 可选参数
    **kwargs
)
```

#### 2. 自动生成输出目录
```python
# 如果未指定 output_dir，自动生成
if output_dir is None:
    file_name = file_path.stem  # 不带扩展名的文件名
    output_dir = file_path.parent / f"unpacked_{file_name}"
```

#### 3. 更新 Function Schema
```python
"parameters": {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Office 文件路径（.docx/.xlsx/.pptx）"
        },
        "output_dir": {
            "type": "string",
            "description": "输出目录路径（可选，默认在源文件目录创建 unpacked_<文件名> 目录）"
        }
    },
    "required": ["path"]  # 只有 path 是必填的
}
```

---

## 📊 测试结果

### Schema 验证
```bash
Name: unpack_office
Required: ['path']
Properties: ['path', 'output_dir']
```

### 执行测试
```bash
# 只提供 path 参数（自动生成 output_dir）
await tool.execute(path="D:/溯源/报告模板/2025年7月16日臭氧垂直.docx")

Success: True
File count: 32
XML count: 23
```

---

## 🎯 使用示例

### 简化调用（推荐）
```python
# 自动生成输出目录：unpacked_2025年7月16日臭氧垂直
unpack_office(path="report.docx")
```

### 自定义输出目录
```python
unpack_office(
    path="data.xlsx",
    output_dir="temp/unpacked_excel/"
)
```

---

## 📝 后续建议

### 其他 Office 工具参数统一

建议检查以下工具，确保参数命名一致：

1. **pack_office**: `input_dir`, `output_file` → 可能需要调整
2. **accept_word_changes**: 参数命名检查
3. **find_replace_word**: 参数命名检查
4. **recalc_excel**: 参数命名检查
5. **add_ppt_slide**: 参数命名检查

### 统一原则

文件操作工具应遵循以下参数命名规范：
- **输入文件**: `path` (与 read_file, edit_file 一致)
- **输出文件**: `output_path` 或 `output_file`
- **输入目录**: `input_dir` 或 `input_path`
- **输出目录**: `output_dir`

---

## ✅ 验证步骤

1. 后端服务自动重新加载（`--reload` 模式）
2. 检查日志确认工具重新注册：
   ```
   [info] tool_registered ... tool=unpack_office
   [info] tool_loaded tool=unpack_office
   ```
3. 测试工具调用成功（如上测试结果）

---

**相关文件**:
- 修改文件: `D:\溯源\backend\app\tools\office\unpack_tool.py`
- 测试脚本: `D:\溯源\test_unpack_params.py`
- 最终诊断: `D:\溯源\backend\docs\unpack_office_final_diagnosis.md`
