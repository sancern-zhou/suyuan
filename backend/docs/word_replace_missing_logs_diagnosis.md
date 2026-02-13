# Word 替换功能问题诊断 - 缺少关键日志

## 问题发现

**日期**：2026-02-11

**症状分析**：

从最新日志（2026-02-11T02:29:14）中发现：

### ✅ 正常输出的日志
```log
word_replace_start
    search_text=数据特征分析：
    search_text_repr='数据特征分析：'
    search_text_bytes=e695b0e68daee789b9e5be81e58886e69e90efbc9a
    replace_text_length=226

word_replace_completed
    replacements=1
    result_type=bool
```

### ❌ 缺失的日志（应该有但没有输出）
```log
word_replace_formatting_cleared  # ❌ 缺失
word_replace_properties_set      # ❌ 缺失
word_replace_executed            # ❌ 缺失
```

---

## 问题分析

### 推测：代码执行路径异常

**预期执行流程**：
1. `word_replace_start` ✅ 输出
2. `find.ClearFormatting()` →
3. `find.Replacement.ClearFormatting()` → **可能在这里卡住或崩溃**
4. `word_replace_formatting_cleared` ❌ **未输出**
5. 设置属性 →
6. `word_replace_properties_set` ❌ **未输出**
7. `find.Execute(Replace=2)` →
8. `word_replace_executed` ❌ **未输出**
9. `word_replace_completed` ✅ 输出

### 可能的原因

1. **`find.Replacement.ClearFormatting()` 抛出异常**
   - 某些 Word 版本可能不支持
   - COM 对象可能未正确初始化

2. **属性设置失败但没有抛出异常**
   - COM 调用静默失败
   - Python 的 win32com 可能吞掉了某些错误

3. **`find.Execute(Replace=2)` 执行了但没有真正替换**
   - 返回 `True`（找到了匹配）
   - 但实际上没有执行替换操作

---

## 修复方案

### 添加异常捕获和验证

```python
# 清除格式（分开执行，捕获异常）
try:
    find.ClearFormatting()
    logger.info("word_replace_find_cleared")
except Exception as e:
    logger.error("word_replace_clear_find_failed", error=str(e))

try:
    find.Replacement.ClearFormatting()
    logger.info("word_replace_replacement_cleared")
except Exception as e:
    logger.error("word_replace_clear_replacement_failed", error=str(e), exc_info=True)

# 设置属性（捕获异常）
try:
    find.Text = search_text
    find.Replacement.Text = replace_text
    find.Forward = True
    find.Wrap = 1
    find.MatchCase = match_case
    find.MatchWholeWord = match_whole_word
    find.MatchWildcards = use_wildcards
except Exception as e:
    logger.error("word_replace_set_properties_failed", error=str(e), exc_info=True)

# 执行替换
result = find.Execute(Replace=2)

# ⚠️ 验证：立即检查文档内容是否真的被修改了
find_verify = doc.Content.Find
find_verify.ClearFormatting()
find_verify.Text = search_text
find_verify.Forward = True
find_verify.Wrap = 1

still_exists = find_verify.Execute()
logger.info(
    "word_replace_verification",
    still_exists_after_replace=still_exists,
    verification_result="FAILED" if still_exists else "SUCCESS"
)
```

---

## 验证方法

重新运行替换操作，然后查看日志：

### 预期日志（如果一切正常）
```log
word_replace_start
word_replace_find_cleared
word_replace_replacement_cleared
word_replace_formatting_cleared
word_replace_properties_set
word_replace_executed
word_replace_verification
    verification_result=SUCCESS  # ✅ 成功
word_replace_completed
```

### 实际日志（如果有问题）
```log
word_replace_start
word_replace_find_cleared
word_replace_clear_replacement_failed  # ❌ 错误
    error=...
word_replace_completed
```

或

```log
word_replace_start
word_replace_find_cleared
word_replace_replacement_cleared
word_replace_formatting_cleared
word_replace_properties_set
word_replace_executed
word_replace_verification
    verification_result=FAILED  # ❌ 失败（文本仍然存在）
word_replace_completed
```

---

## 下一步行动

1. **重新测试**：运行替换操作并查看详细日志
2. **检查验证结果**：`verification_result` 字段
   - `SUCCESS` = 替换成功
   - `FAILED` = 替换失败（文本仍然存在）
3. **根据错误日志**：定位具体的问题点

---

## 最终解决方案（如果验证失败）

如果 `verification_result=FAILED`（文本仍然存在），说明替换确实没有生效，那么：

### 方案1：使用手动替换（强制方法）
```python
replacements = 0
while find.Execute(FindText=search_text):
    found_range = doc.Range(find.Parent.Start, find.Parent.End)
    found_range.Delete()
    found_range.InsertAfter(replace_text)
    replacements += 1
    if replacements > 1000:
        break
```

### 方案2：使用 Selection 对象
```python
# 使用 Selection 而不是 Find
doc.Content.Select()
selection = word.Selection
selection.Find.Text = search_text
selection.Find.Forward = True
selection.Find.Execute()
if selection.Find.Found:
    selection.TypeText(replace_text)
```

---

## 总结

**问题**：中间的日志缺失，说明某个步骤卡住或失败了

**诊断方法**：
1. 添加 try-except 捕获每个步骤的异常
2. 添加验证步骤检查替换是否真的生效
3. 根据新的日志输出定位具体问题

**等待结果**：重新测试并查看新的详细日志
