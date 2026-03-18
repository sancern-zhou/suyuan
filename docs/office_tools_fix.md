# Office 工具修复说明

## 问题描述

用户报告 Word 和 PPT 工具反馈替换成功，但文档实际并未修改。

## 根本原因

### Word 工具问题

1. **使用了错误的替换方法**
   - **错误方式**：使用 `Selection.Find` + `Selection.TypeText()`
     - `find.Execute()` 会选中匹配的文本
     - 但 `Selection.TypeText(new_text)` 只是在当前光标位置输入文本，而不是替换选中的文本
     - 结果：文本被插入而不是替换，或者根本没有修改

   - **正确方式**：使用 `Content.Find.Execute(Replace=2)`
     - `Content.Find` 在整个文档范围内搜索
     - `Execute(Replace=2)` 中的 `2` 是 `wdReplaceAll` 常量，表示替换所有匹配项
     - 这会直接修改文档内容，返回值是替换的次数

2. **search_and_replace 中的重复计算问题**
   - 先用 `temp_find.Execute()` 循环收集匹配项
   - 再用 `find.Execute()` 循环执行替换
   - 由于两次循环是独立的，会导致计数不准确
   - 修复：在替换之前收集匹配项，然后一次性替换所有

3. **batch_replace 中的相同问题**
   - 同样使用了 `Selection.Find` + `Selection.TypeText()`
   - 修复：改用 `Content.Find.Execute(Replace=2)`

### PPT 工具问题

1. **replace_text 方法实现正确**
   - 使用了 `text_range.Replace()` 方法
   - 这个方法会正确替换文本

2. **search_and_replace 方法中的逻辑错误**
   - 对每个形状都执行替换，即使形状不包含搜索文本
   - 这导致 `replacements` 计数不准确
   - 修复：只在包含搜索文本的形状中执行替换

## 修复方案

### Word 工具修复

#### 1. replace_text 方法

```python
# 修复前（错误）
find = self.app.Selection.Find
# ... 配置 ...
replacements = 0
while find.Execute():
    self.app.Selection.TypeText(new_text)  # 错误：不会替换选中的文本
    replacements += 1

# 修复后（正确）
find = doc.Content.Find
# ... 配置 ...
replacements = find.Execute(Replace=2)  # 正确：一次性替换所有匹配项
```

#### 2. search_and_replace 方法

```python
# 修复前
# 先收集匹配（循环）
while temp_find.Execute():
    matches.append(...)

# 再执行替换（又是一个循环）
while find.Execute():
    self.app.Selection.TypeText(replace_text)  # 错误的方式
    replacements += 1

# 修复后
# 收集前10个匹配项
match_count = 0
while temp_find.Execute() and match_count < 10:
    matches.append(...)
    match_count += 1

# 一次性替换所有
replacements = find.Execute(Replace=2)
```

#### 3. batch_replace 方法

```python
# 修复前（错误）
find = self.app.Selection.Find
count = 0
while find.Execute():
    self.app.Selection.TypeText(new_text)  # 错误
    count += 1

# 修复后（正确）
find = doc.Content.Find
count = find.Execute(Replace=2)  # 正确
```

### PPT 工具修复

#### search_and_replace 方法

```python
# 修复前
for shape in slide.Shapes:
    if shape.HasTextFrame:
        # 无论是否包含搜索文本，都执行替换
        text_range.Replace(...)
        replacements += 1  # 错误的计数

# 修复后
for shape in slide.Shapes:
    if shape.HasTextFrame:
        # 先检查是否包含搜索文本
        if contains_text:
            # 只在包含文本时才执行替换
            text_range.Replace(...)
            replacements += 1  # 正确的计数
```

## Word COM 常量说明

| 常量 | 值 | 说明 |
|------|---|------|
| `wdFindContinue` | 1 | 继续搜索（从文档开头重新开始） |
| `wdReplaceOne` | 1 | 替换一个匹配项 |
| `wdReplaceAll` | 2 | 替换所有匹配项 |

## 关键要点

1. **使用 `Content.Find` 而不是 `Selection.Find`**
   - `Content.Find` 在整个文档范围内操作
   - `Selection.Find` 依赖于当前选择位置，不可靠

2. **使用 `Execute(Replace=2)` 而不是循环替换**
   - `Execute(Replace=2)` 一次性替换所有匹配项
   - 循环 `Execute()` + `TypeText()` 的方式不可靠

3. **正确处理替换次数**
   - `Execute(Replace=2)` 返回值就是替换次数
   - 不需要手动循环计数

4. **PPT 中的特殊处理**
   - PPT 没有全局替换方法，需要遍历所有形状
   - 需要先检查形状是否包含搜索文本，再执行替换

## 测试建议

1. 创建测试文档，包含多个相同的待替换文本
2. 执行替换操作
3. 验证：
   - 所有匹配的文本都被替换
   - 替换次数准确
   - 文档保存成功
   - 原始文档被正确修改（如果没有指定 save_as）

## 版本更新

- Word 工具：v2.1.0（添加 search_and_replace）→ v2.1.1（修复替换问题）
- PPT 工具：v2.1.0（添加 search_and_replace）→ v2.1.1（修复替换问题）
