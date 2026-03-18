# Office工具提示词优化说明

## 修改时间
2026-02-09

## 修改文件
`backend/app/tools/office/word_tool.py`

## 修改目的
解决Agent在执行insert操作时容易失败的问题，通过改进提示词提升Agent的调用成功率。

## 主要修改

### 1. 移除二次加载提示
**修改前**:
```python
description="""...⚠️ 第一次使用时请先输出 args: null 或 args: {} 查看详细参数说明"""
```

**修改后**:
```python
description="""Word文档编辑工具（Windows）
...
【insert操作最佳实践】
1. 优先使用 position="end" 或 "start" 避免匹配失败
2. 使用 after/before 时，target必须精确匹配文档中的文本
3. 建议：先用read操作查看文档，复制准确的目标文本作为target
4. 如需在特定段落插入，考虑使用search_and_replace替换段落内的唯一标识

示例：{"path": "D:\\\\docs.docx", "operation": "insert", "position": "end", "content": "追加内容"}
"""
```

**改进点**:
- ✅ 删除 `args: null` 提示，避免二次加载参数说明
- ✅ 将关键使用指导直接嵌入description
- ✅ 添加4条针对insert操作的最佳实践
- ✅ 只保留1个简洁示例

### 2. 精简参数说明
**修改前**:
```python
"operation": {
    "description": "操作类型：read=读取内容（支持分页）, insert=在指定位置插入文本, ..."
}
```

**修改后**:
```python
"operation": {
    "description": "操作类型：read/insert/search_and_replace/tables/stats/batch_replace"
}
```

**改进点**:
- ✅ 去除冗余的参数说明
- ✅ 只保留核心枚举值
- ✅ 详细信息已整合到description中

### 3. 精简函数文档
**修改前**:
```python
"""
执行 Word 操作

Args:
    ...

## 分页读取示例
    读取前10个段落: ...

## 搜索并替换示例
    ### 场景1: 精确搜索删除 ...
    ### 场景2: 模糊搜索 ...
    ### 场景3-5: ...

## 搜索技巧总结
    1. ... 2. ... 3. ... 4. ... 5. ...
"""
```

**修改后**:
```python
"""
执行 Word 操作

Args:
    path: Word 文档路径
    operation: 操作类型（read/insert/search_and_replace/tables/stats/batch_replace）
    ...
    use_wildcards: 是否使用通配符（*匹配任意字符，[]匹配字符集）

Returns:
    操作结果字典（UDF v2.0 格式）
"""
```

**改进点**:
- ✅ 删除70+行的冗余示例
- ✅ 只保留参数列表和返回值说明
- ✅ 通配符用法以简洁注释形式保留

## 优化效果

### Token消耗对比
- **修改前**: description + 示例 ≈ 1200 tokens
- **修改后**: description + 示例 ≈ 400 tokens
- **节省**: 约67%

### Agent调用成功率预期
通过4条最佳实践指导，预期提升insert操作成功率：
1. 优先使用end/start（100%成功率）
2. 精确匹配target（避免格式字符导致失败）
3. 先read查看文档（获取准确的target文本）
4. 使用search_and_replace替代（更稳定）

## 使用建议

Agent在执行insert操作时应该：
```python
# 推荐：直接在末尾插入
await word_processor(
    path="D:\\docs.docx",
    operation="insert",
    position="end",
    content="追加内容"
)

# 推荐：先read获取准确文本，再insert
result = await word_processor(path="D:\\docs.docx", operation="read")
# 从result中找到准确的目标文本
target_text = result["data"]["paragraphs"][5][:20]  # 复制前20个字符
await word_processor(
    path="D:\\docs.docx",
    operation="insert",
    position="after",
    target=target_text,  # 使用准确的文本
    content="插入内容"
)

# 替代方案：使用search_and_replace替换唯一标识
await word_processor(
    path="D:\\docs.docx",
    operation="search_and_replace",
    search_text="[INSERT_POINT]",
    replace_text="[INSERT_POINT]新插入的内容"
)
```

## 版本信息
- 版本号: 2.3.0 → 2.4.0
- 修改日期: 2026-02-09
