# read_excel_charts 函数使用示例

## 概述

`read_excel_charts` 函数用于安全地读取Excel文件中的图表信息，包括图表类型、标题、数据范围、类别范围等。

## 函数签名

```python
def read_excel_charts(file_path, sheet_name=None):
    '''安全地读取Excel文件中的图表信息

    Args:
        file_path: Excel文件路径
        sheet_name: 工作表名称（None表示所有工作表）

    Returns:
        dict: {
            'file': 文件名,
            'total_charts': 总图表数,
            'charts': [
                {
                    'sheet': 工作表名,
                    'index': 图表索引,
                    'type': 图表类型,
                    'title': 图表标题,
                    'series': [
                        {
                            'title': 系列标题,
                            'title_ref': 标题引用,
                            'values_range': 数据范围,
                            'category_range': 类别范围
                        }
                    ]
                }
            ]
        }
    '''
```

## 使用示例

### 示例1：读取所有工作表的图表

```python
# 读取Excel文件中的所有图表
result = read_excel_charts('report.xlsx')

# 显示结果
print(f"文件: {result['file']}")
print(f"总图表数: {result['total_charts']}")

for chart in result['charts']:
    print(f"\n图表: {chart['title']}")
    print(f"  类型: {chart['type']}")
    print(f"  工作表: {chart['sheet']}")

    for series in chart['series']:
        print(f"  系列: {series['title']}")
        print(f"    数据范围: {series['values_range']}")
        print(f"    类别范围: {series['category_range']}")
```

### 示例2：读取特定工作表的图表

```python
# 只读取"Sheet1"工作表的图表
result = read_excel_charts('report.xlsx', sheet_name='Sheet1')

print(f"Sheet1 中的图表数: {result['total_charts']}")
```

### 示例3：在Agent系统中使用

```python
# 用户上传Excel文件后，Agent可以使用以下方式分析图表
result = read_excel_charts('/path/to/uploaded/file.xlsx')

# 分析图表配置
if result['total_charts'] > 0:
    analysis = f"文件包含 {result['total_charts']} 个图表:\n\n"

    for chart in result['charts']:
        analysis += f"1. {chart['title']} ({chart['type']})\n"
        analysis += f"   - 工作表: {chart['sheet']}\n"

        if 'series' in chart:
            for series in chart['series']:
                if 'values_range' in series:
                    analysis += f"   - 数据范围: {series['values_range']}\n"
                if 'category_range' in series:
                    analysis += f"   - 类别范围: {series['category_range']}\n"

        analysis += "\n"

    print(analysis)
```

## 支持的图表类型

该函数支持所有openpyxl支持的图表类型，包括但不限于：

- BarChart（柱状图）
- LineChart（折线图）
- PieChart（饼图）
- AreaChart（面积图）
- ScatterChart（散点图）
- 等等

## 错误处理

函数内部实现了完善的错误处理机制：

1. **属性访问安全**：使用try-catch包裹所有属性访问，避免因对象结构不同导致的错误
2. **多路径尝试**：针对不同版本的Excel文件，尝试多种可能的属性路径
3. **错误信息记录**：如果某个属性获取失败，会在结果中记录错误信息

## 输出格式说明

### 图表信息

- `sheet`: 图表所在的工作表名称
- `index`: 图表在工作表中的索引（从0开始）
- `type`: 图表类型（如"BarChart"、"LineChart"等）
- `title`: 图表标题（如果没有标题，则显示为"图表N"）

### 系列信息

- `title`: 系列标题（如果没有标题，则显示为"系列N"）
- `title_ref`: 系列标题的单元格引用（如"[1]全国PM2.5!$O$1"）
- `values_range`: 数据值的单元格范围（如"[1]全国PM2.5!$O$2:$O$32"）
- `category_range`: 类别的单元格范围（如"[1]全国PM2.5!$M$2:$M$32"）

## 注意事项

1. **文件格式**：仅支持.xlsx格式（Excel 2007+），不支持.xls格式
2. **数据模式**：必须使用`data_only=False`模式加载工作簿，以便访问图表对象
3. **单元格引用**：返回的单元格引用包含工作表名称，格式为"[工作表名]!单元格范围"
4. **兼容性**：不同版本的Excel创建的图表可能结构不同，函数已实现多路径尝试以提高兼容性

## 更新日志

### 2026-04-16
- 修复了图表属性访问错误的问题
- 支持了多种图表数据来源（val.numRef、cat.strRef等）
- 添加了系列标题引用的提取
- 改进了错误处理机制
