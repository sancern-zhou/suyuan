# Word 文档图片提取功能 - 使用说明

## 功能概述

`word_processor` 工具新增 `extract_images` 操作，可以提取 Word 文档中的所有图片并保存到本地目录，为后续使用 `analyze_image` 工具进行图片分析做准备。

## 操作说明

### extract_images 操作

**功能**：提取 Word 文档中的所有内嵌图片（InlineShapes）

**参数**：
- `path`（必填）：Word 文档路径
- `output_dir`（可选）：输出目录，默认为 `backend_data_registry/temp_images`

**返回格式**：
```json
{
  "status": "success",
  "success": true,
  "data": {
    "images": [
      {
        "index": 0,
        "path": "D:/溯源/backend_data_registry/temp_images/document_image_0.png",
        "width": 800,
        "height": 600
      },
      {
        "index": 1,
        "path": "D:/溯源/backend_data_registry/temp_images/document_image_1.png",
        "width": 1200,
        "height": 800
      }
    ],
    "count": 2
  },
  "metadata": {
    "schema_version": "v2.0",
    "generator": "word_processor",
    "operation": "extract_images"
  },
  "summary": "提取了2张图片"
}
```

## 典型使用场景

### 场景1：提取并分析所有图片

```
用户：读取这个 Word 文档并分析其中的所有图片

Agent 执行流程：
1. word_processor(path="report.docx", operation="extract_images")
   → 返回2张图片的路径列表

2. 并行调用 analyze_image：
   - analyze_image(path="report_image_0.png", operation="analyze")
   - analyze_image(path="report_image_1.png", operation="analyze")

3. 返回完整的分析结果
```

### 场景2：选择性分析图片

```
用户：只分析 Word 文档的第1张和第3张图片

Agent 执行流程：
1. word_processor(path="document.docx", operation="extract_images")
   → 返回：[image_0, image_1, image_2, image_3]

2. 只分析 index=0 和 index=2 的图片：
   - analyze_image(path="document_image_0.png")
   - analyze_image(path="document_image_2.png")
```

### 场景3：基于条件过滤图片

```
用户：分析 Word 文档中宽度大于1000的图片

Agent 执行流程：
1. word_processor(path="presentation.docx", operation="extract_images")
   → 返回包含 width/height 的图片列表

2. 过滤条件：width > 1000
   → 只选择符合条件图片进行 analyze_image
```

## 工作流程示例

### 完整工作流

```
用户请求
  ↓
【步骤1】提取图片
  word_processor(operation="extract_images")
  ↓
  返回：images列表（index, path, width, height）
  ↓
【步骤2】Agent 选择需要分析的图片
  （根据用户需求或返回的元数据选择）
  ↓
【步骤3】分析选中的图片
  analyze_image(path="xxx_image_0.png")
  analyze_image(path="xxx_image_2.png")
  ↓
【步骤4】返回完整结果
  （文本内容 + 图片分析结果）
```

## 技术细节

### 图片存储位置

**默认目录**：`backend_data_registry/temp_images`

**命名规则**：`{文档名称}_image_{索引}.png`

**示例**：
- 文档：`report.docx`
- 图片：`report_image_0.png`, `report_image_1.png`, ...

### 图片尺寸单位

- 返回的 `width` 和 `height` 单位为 points（磅）
- 1 inch = 72 points
- 1 cm ≈ 28.35 points

### 支持的图片格式

**输入**：Word 文档中的所有 InlineShapes（内嵌图片）
**输出**：PNG 格式

### 限制说明

1. **只提取内嵌图片**：不提取浮动图片（Shapes）
2. **不保留原始格式**：统一转换为 PNG
3. **覆盖已存在文件**：如果同名文件已存在，会被覆盖

## 错误处理

### 文档打开失败
```json
{
  "status": "failed",
  "error": "无法打开文档",
  "summary": "操作失败"
}
```

### 文档中没有图片
```json
{
  "status": "success",
  "data": {
    "images": [],
    "count": 0
  },
  "summary": "提取了0张图片"
}
```

### 部分图片提取失败
```json
{
  "status": "success",
  "data": {
    "images": [
      // 成功提取的图片
    ],
    "count": 2
  },
  "summary": "提取了2张图片"
}
// 日志中会记录失败的图片索引
```

## 与其他工具的配合

### 与 analyze_image 配合

```python
# 步骤1：提取图片
result1 = await word_processor.execute(
    path="document.docx",
    operation="extract_images"
)

# 步骤2：获取图片路径
images = result1["data"]["images"]

# 步骤3：分析图片
for img in images:
    if img["index"] in [0, 2]:  # 只分析第1和第3张
        result2 = await analyze_image.execute(
            path=img["path"],
            operation="analyze"
        )
        print(result2["data"]["analysis"])
```

### 与 read 操作配合

```python
# 步骤1：读取文档文本
text_result = await word_processor.execute(
    path="document.docx",
    operation="read"
)

# 步骤2：提取图片
image_result = await word_processor.execute(
    path="document.docx",
    operation="extract_images"
)

# 步骤3：综合处理
content = text_result["data"]["content"]
images = image_result["data"]["images"]
```

## 扩展到其他文档类型

未来计划支持：
- **Excel**：`excel_processor(operation="extract_images")`
- **PowerPoint**：`ppt_processor(operation="extract_images")`
- **PDF**：可能需要专门的 PDF 图片提取工具

## 测试

运行测试脚本：
```bash
cd backend
python test_extract_images.py
```

测试脚本会：
1. 打开指定的 Word 文档
2. 提取所有图片
3. 显示每张图片的路径、尺寸、文件大小
4. 验证文件是否正确保存
