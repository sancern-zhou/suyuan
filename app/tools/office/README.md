# Office Win32 自动化工具使用指南

## 快速开始

### 1. 安装依赖

```bash
pip install pywin32
```

### 2. 基本使用

#### Word 文档处理

```python
from app.tools.office import WordWin32Tool

# 创建工具实例
word = WordWin32Tool(visible=False)

try:
    # 读取文档内容
    result = word.read_all_text(r"D:\report.docx")
    print(result['summary'])
    print(f"段落数: {result['stats']['paragraph_count']}")

    # 替换文本
    result = word.replace_text(
        r"D:\report.docx",
        old_text="{{name}}",
        new_text="张三",
        save_as=r"D:\report_张三.docx"
    )
    print(f"替换了 {result['replacements']} 处")

    # 读取表格
    result = word.read_tables(r"D:\report.docx")
    print(f"共 {result['table_count']} 个表格")

finally:
    # 关闭 Word 应用程序
    word.close_app()
```

#### Excel 表格处理

```python
from app.tools.office import ExcelWin32Tool

excel = ExcelWin32Tool(visible=False)

try:
    # 列出所有工作表
    result = excel.list_sheets(r"D:\data.xlsx")
    print(f"工作表: {result['sheets']}")

    # 读取单元格
    result = excel.read_cell(
        r"D:\data.xlsx",
        sheet_name="Sheet1",
        cell_address="A1"
    )
    print(f"A1 = {result['value']}")

    # 读取范围
    result = excel.read_range(
        r"D:\data.xlsx",
        sheet_name="Sheet1",
        range_address="A1:C10"
    )
    print(f"读取了 {result['rows']} 行 {result['cols']} 列")

    # 写入单元格
    result = excel.write_cell(
        r"D:\data.xlsx",
        sheet_name="Sheet1",
        cell_address="B2",
        value=12345,
        save_as=r"D:\data_modified.xlsx"
    )

finally:
    excel.close_app()
```

#### PowerPoint 演示文稿处理

```python
from app.tools.office import PPTWin32Tool

ppt = PPTWin32Tool(visible=False)

try:
    # 列出所有幻灯片
    result = ppt.list_slides(r"D:\presentation.pptx")
    for slide in result['slides']:
        print(f"{slide['index']}. {slide['title']}")

    # 读取所有文本
    result = ppt.read_all_text(r"D:\presentation.pptx")
    print(f"共 {result['slide_count']} 张幻灯片")

    # 替换文本
    result = ppt.replace_text(
        r"D:\presentation.pptx",
        old_text="{{company}}",
        new_text="XX公司",
        save_as=r"D:\presentation_XX公司.pptx"
    )
    print(f"替换了 {result['replacements']} 处")

finally:
    ppt.close_app()
```

### 3. 使用上下文管理器（推荐）

```python
from app.tools.office import WordWin32Tool

# 使用 with 语句自动关闭应用程序
with WordWin32Tool(visible=False) as word:
    result = word.read_all_text(r"D:\report.docx")
    print(result['summary'])

# 自动调用 word.close_app()
```

## API 参考

### WordWin32Tool

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `read_all_text(file_path)` | 读取所有文本 | `{status, text, paragraphs, stats}` |
| `replace_text(file_path, old_text, new_text, save_as=None)` | 替换文本 | `{status, replacements, output_file}` |
| `read_tables(file_path)` | 读取所有表格 | `{status, tables, table_count}` |
| `batch_replace(file_path, replacements, save_as=None)` | 批量替换 | `{status, results, total_replacements}` |
| `get_document_stats(file_path)` | 获取文档统计 | `{status, stats}` |

### ExcelWin32Tool

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `list_sheets(file_path)` | 列出工作表 | `{status, sheets, sheet_count}` |
| `read_cell(file_path, sheet_name, cell_address)` | 读取单元格 | `{status, value, formula}` |
| `write_cell(file_path, sheet_name, cell_address, value, save_as=None)` | 写入单元格 | `{status, value, output_file}` |
| `read_range(file_path, sheet_name, range_address)` | 读取范围 | `{status, data, rows, cols}` |
| `write_range(file_path, sheet_name, range_address, data, save_as=None)` | 写入范围 | `{status, cells_written, output_file}` |
| `get_workbook_stats(file_path)` | 获取工作簿统计 | `{status, stats}` |

### PPTWin32Tool

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `list_slides(file_path)` | 列出幻灯片 | `{status, slides, slide_count}` |
| `read_all_text(file_path)` | 读取所有文本 | `{status, slides, slide_count}` |
| `replace_text(file_path, old_text, new_text, save_as=None)` | 替换文本 | `{status, replacements, output_file}` |
| `get_presentation_stats(file_path)` | 获取演示文稿统计 | `{status, stats}` |

## 测试

运行测试脚本：

```bash
cd D:\溯源\backend
python tests\test_office_win32.py
```

测试脚本会提示你输入测试文件路径，并执行各种操作。

## 常见使用场景

### 场景1: 批量生成报告

```python
from app.tools.office import WordWin32Tool

data_list = [
    {"name": "张三", "score": 95},
    {"name": "李四", "score": 87},
    {"name": "王五", "score": 92}
]

with WordWin32Tool(visible=False) as word:
    for data in data_list:
        word.replace_text(
            r"D:\template.docx",
            old_text="{{name}}",
            new_text=data['name'],
            save_as=f"D:\\reports\\report_{data['name']}.docx"
        )

        # 继续替换其他内容
        word.replace_text(
            f"D:\\reports\\report_{data['name']}.docx",
            old_text="{{score}}",
            new_text=str(data['score'])
        )
```

### 场景2: 提取 Excel 数据

```python
from app.tools.office import ExcelWin32Tool

with ExcelWin32Tool(visible=False) as excel:
    # 读取整个表格
    result = excel.read_range(
        r"D:\data.xlsx",
        sheet_name="Sheet1",
        range_address="A1:D100"
    )

    # 处理数据
    for row in result['data']:
        print(row)
```

### 场景3: 批量修改 PPT

```python
from app.tools.office import PPTWin32Tool

replacements = {
    "{{company}}": "XX公司",
    "{{date}}": "2026年2月7日",
    "{{author}}": "张三"
}

with PPTWin32Tool(visible=False) as ppt:
    for old_text, new_text in replacements.items():
        ppt.replace_text(
            r"D:\presentation.pptx",
            old_text=old_text,
            new_text=new_text,
            save_as=r"D:\presentation_modified.pptx"
        )
```

## 注意事项

1. **文件路径**: 必须使用绝对路径或确保当前工作目录正确
2. **文件关闭**: 使用 `close_app()` 或上下文管理器确保正确关闭 Office 应用
3. **错误处理**: 所有方法都返回包含 `status` 字段的字典，检查 `status == "success"` 确认操作成功
4. **性能**: win32com 性能较慢，不适合批量处理大量文件
5. **Windows only**: 此工具仅支持 Windows 平台

## 故障排除

### 问题1: 无法创建 COM 对象

```
错误: Cannot create ActiveX component
```

**解决方法**:
- 确保已安装 Microsoft Office
- 以管理员身份运行脚本
- 修复 Office 安装

### 问题2: 文件打开失败

```
错误: 无法打开文档
```

**解决方法**:
- 检查文件路径是否正确
- 确保文件未被其他程序占用
- 检查文件权限

### 问题3: 应用程序未关闭

```
问题: Word/Excel 进程残留
```

**解决方法**:
- 使用上下文管理器 (`with` 语句)
- 确保调用 `close_app()`
- 手动结束任务管理器中的进程

## 进阶使用

### 自定义 Excel 公式

```python
excel = ExcelWin32Tool(visible=False)

workbook = excel.open_workbook(r"D:\data.xlsx", read_only=False)
sheet = workbook.Worksheets("Sheet1")

# 写入公式
sheet.Range("C1").Formula = "=SUM(A1:B1)"

excel.save_workbook(workbook, r"D:\data_with_formula.xlsx")
excel.close_workbook(workbook)
excel.close_app()
```

### 操作 Word 表格

```python
word = WordWin32Tool(visible=False)

doc = word.open_document(r"D:\report.docx", read_only=False)

# 访问第一个表格
if doc.Tables.Count > 0:
    table = doc.Tables(1)

    # 读取单元格
    cell_value = table.Cell(1, 1).Range.Text

    # 写入单元格
    table.Cell(2, 2).Range.Text = "新内容"

word.save_document(doc, r"D:\report_modified.docx")
word.close_document(doc)
word.close_app()
```

## 更多信息

- Office 开发文档: https://docs.microsoft.com/zh-cn/office/vba/api/overview/
- pywin32 文档: https://github.com/mhammond/pywin32
