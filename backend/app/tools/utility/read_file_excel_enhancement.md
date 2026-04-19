# read_file 工具 Excel 文件检测增强

## 更新日期
2026-04-16

## 功能说明

增强了 `read_file` 工具，使其能够自动识别 Excel 文件（.xlsx, .xls, .xlsm），并返回友好的提示信息，引导用户使用 `execute_python` 工具来读取 Excel 文件。

## 主要改进

### 1. 新增 Excel 文件类型检测

**支持的 Excel 格式**：
- `.xlsx` - Excel 2007+ 工作簿
- `.xls` - Excel 97-2003 工作簿
- `.xlsm` - Excel 启用宏的工作簿

### 2. 智能提示信息

当 `read_file` 检测到 Excel 文件时，返回以下信息：

```json
{
  "success": false,
  "data": {
    "error": "Excel 文件需要使用 execute_python 工具读取",
    "file_type": "Excel",
    "file_name": "example.xlsx",
    "file_size_mb": 0.5,
    "suggested_tool": "execute_python",
    "available_functions": {
      "read_excel": "读取 Excel 文件的数据和结构信息",
      "analyze_excel_template": "分析 Excel 模板的结构和图表配置",
      "create_excel_report": "创建 Excel 报告（支持数据和图表）"
    },
    "usage_example": "..."
  },
  "summary": "📊 Excel 文件: example.xlsx (0.5 MB) - 请使用 execute_python 工具读取"
}
```

### 3. 使用示例

返回的使用示例包含三个场景：

#### 场景1：读取 Excel 数据
```python
result = read_excel("path/to/file.xlsx")
print(result['sheets'])  # 工作表列表
print(result['data']['Sheet1'])  # 数据
```

#### 场景2：分析 Excel 模板
```python
template = analyze_excel_template("path/to/file.xlsx")
print(template['sheets'])  # 工作表结构
print(template['charts'])  # 图表配置
```

#### 场景3：生成 Excel 报告
```python
data = [{"列1": "值1", "列2": "值2"}]
report = create_excel_report(data, output_name="new_report.xlsx")
print(report['file_path'])  # 生成的文件路径
```

## 技术实现

### 修改的文件

`backend/app/tools/utility/read_file_tool.py`

### 主要改动

1. **添加 Excel 扩展名定义**
```python
EXCEL_EXTENSIONS = {'.xlsx', '.xls', '.xlsm'}
```

2. **添加 Excel 文件类型检测**
```python
is_excel = file_ext in self.EXCEL_EXTENSIONS
```

3. **添加 Excel 文件处理分支**
```python
elif is_excel:
    return await self._handle_excel_file(resolved_path)
```

4. **新增 `_handle_excel_file` 方法**
```python
async def _handle_excel_file(self, file_path: Path) -> Dict[str, Any]:
    """处理 Excel 文件，提示用户使用 execute_python 工具"""
    # 返回提示信息和 Excel 处理函数说明
```

5. **更新工具描述**
在工具描述中添加了 Excel 文件处理说明和 execute_python 工具的介绍。

## 用户体验改进

### Before（改进前）
```
❌ 读取失败: 文本编码错误: example.xlsx
```

### After（改进后）
```
📊 Excel 文件: example.xlsx (0.5 MB) - 请使用 execute_python 工具读取

建议工具: execute_python

可用函数:
  - read_excel: 读取 Excel 文件的数据和结构信息
  - analyze_excel_template: 分析 Excel 模板的结构和图表配置
  - create_excel_report: 创建 Excel 报告（支持数据和图表）

使用示例:
  [详细的三种使用场景示例]
```

## 兼容性

- ✅ **向后兼容**：不影响现有功能
- ✅ **文本文件读取**：正常工作（已测试）
- ✅ **其他文件类型**：PDF、DOCX、图片等不受影响
- ✅ **错误处理**：优雅降级，不影响其他文件读取

## 测试

**测试文件**: `backend/test_read_file_excel_detection.py`

**测试结果**:
```
✅ Excel 文件检测正常
   - 正确识别为 Excel 文件
   - 建议使用 execute_python 工具
   - 提供了可用的函数列表和使用示例
✅ 文本文件读取正常（不受影响）
```

## 相关文档

- `execute_python_excel_guide.md` - Excel 功能完整指南
- `execute_python_excel_examples.md` - Excel 使用示例
- `execute_python_excel_changelog.md` - Excel 更新日志

## 使用场景

### 场景1：用户尝试用 read_file 读取 Excel
```
用户: 读取这个文件 example.xlsx
Agent: [调用 read_file]
read_file: 📊 Excel 文件: example.xlsx (0.5 MB) - 请使用 execute_python 工具读取
Agent: [理解提示，改用 execute_python]
execute_python: [成功读取 Excel 数据]
```

### 场景2：Agent 自动识别并切换工具
```
用户: 分析这个 Excel 模板
Agent: [尝试 read_file]
read_file: [返回 Excel 提示]
Agent: [识别到 Excel 文件，自动使用 execute_python]
execute_python: [调用 analyze_excel_template]
Agent: [返回模板分析结果]
```

## 未来改进

- [ ] 支持检测 CSV 文件并提示使用 execute_python
- [ ] 提供更详细的 Excel 文件信息（工作表数量、行列数等）
- [ ] 支持 Excel 文件的预览功能（前几行数据）
- [ ] 集成到 Agent 的自动工具选择逻辑中

## 总结

这次增强显著改善了用户体验：

1. **清晰的错误提示** - 不再显示模糊的"编码错误"
2. **正确的工具引导** - 直接建议使用 execute_python
3. **完整的使用示例** - 提供三种常见场景的示例代码
4. **零影响** - 不影响现有功能，完全向后兼容

现在用户和 Agent 都能更好地处理 Excel 文件了！
