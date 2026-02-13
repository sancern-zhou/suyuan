# Word 替换功能最终修复 - 完全使用手动循环方法

## 问题回顾

**日期**：2026-02-11

**根本问题**：
- `wdReplaceAll` 方法在某些 Word 版本中存在 bug
- 即使 `find.Execute(Replace=2)` 返回 `True`，实际替换也可能不生效
- 验证日志显示：`verification_result=FAILED`，`still_exists_after_replace=True`

**参考**：[PyWin32 GitHub Issue #726](https://github.com/mhammond/pywin32/issues/726)

---

## 最终解决方案

### 完全使用手动循环方法（Delete + InsertAfter）

**废弃** `wdReplaceAll` 方法，**完全使用手动循环**：
- 不受 255 字符限制
- 避免 `wdReplaceAll` 的 bug
- 真正可靠地执行替换操作

### 两步策略（处理替换文本包含搜索文本的情况）

#### 情况1：替换文本不包含搜索文本
直接使用手动循环：
```python
while find.Execute():
    found_range = doc.Range(find.Parent.Start, find.Parent.End)
    found_range.Delete()
    found_range.InsertAfter(replace_text)
    find.Parent.Start = found_range.End
    find.Parent.End = doc.Content.End
```

#### 情况2：替换文本包含搜索文本
使用**占位符两步策略**：
```python
# 第一步：将搜索文本替换为唯一占位符
placeholder = f"__TEMP_REPLACE_{uuid.uuid4().hex}__"
while find.Execute():  # 查找 search_text
    found_range.Delete()
    found_range.InsertAfter(placeholder)

# 第二步：将占位符替换为目标文本
while find.Execute():  # 查找 placeholder
    found_range.Delete()
    found_range.InsertAfter(replace_text)
```

**优势**：
- 避免无限循环（替换文本包含搜索文本时）
- 安全可靠（占位符唯一性保证）
- 位置保护机制防止重复处理

---

## 实现细节

### 1. 检测替换文本是否包含搜索文本
```python
replace_text_contains_search = search_text in replace_text
```

### 2. 位置保护机制
```python
last_position = 0
while find.Execute():
    current_position = found_range.Start
    if current_position <= last_position:
        break  # 位置未前进，跳出循环
    last_position = current_position
```

### 3. 迭代次数限制
```python
MAX_ITERATIONS = 100
if replacements >= MAX_ITERATIONS:
    break
```

---

## 测试结果

### 测试1：替换文本不包含搜索文本
```
搜索文本: 臭氧雷达分析：
替换文本长度: 43 字符
replace_text_contains_search=False
方法: word_replace_direct_loop
结果: 替换成功（1处）
验证: 成功 - 原搜索文本已被替换
```

### 测试2：替换文本包含搜索文本
```
搜索文本: 数据
替换文本长度: 52 字符
replace_text_contains_search=True
方法: word_replace_using_placeholder
占位符: __TEMP_REPLACE_67ebddeb8bdd4d8b92ae494936453c50__
第一步: placeholder_replacements=2
第二步: final_replacements=2
结果: 替换成功（2处）
```

---

## 代码变更

### `search_and_replace` 方法
- **移除**：`wdReplaceAll` 分支（`if len(replace_text) <= 255`）
- **新增**：`replace_text_contains_search` 检测
- **新增**：占位符两步策略
- **保留**：手动循环方法作为唯一实现

### `batch_replace` 方法
- **移除**：`wdReplaceAll` 调用
- **新增**：手动循环实现批量替换

---

## 日志输出

### 直接循环模式
```log
word_replace_start
  method=manual_delete_insert
  replace_text_contains_search=False

word_replace_direct_loop
  method=delete_and_insert

word_replace_manual_loop_start

word_replace_iteration
  iteration=1
  current_position=894

word_replace_delete_success
word_replace_insert_success

word_replace_completed
  replacements=1
```

### 占位符模式
```log
word_replace_start
  method=manual_delete_insert
  replace_text_contains_search=True

word_replace_using_placeholder
  placeholder=__TEMP_REPLACE_...__
  reason=replace_text_contains_search=True

word_replace_step1_completed
  placeholder_replacements=2

word_replace_step2_completed
  final_replacements=2

word_replace_completed
  replacements=2
```

---

## 性能说明

- **手动循环**：比 `wdReplaceAll` 慢，但**真正可靠**
- **占位符两步**：需要两次循环，但**避免了无限循环风险**
- **适用场景**：所有替换操作，不受长度限制

---

## 修复状态

| 方法 | 状态 | 原因 |
|------|------|------|
| wdReplaceAll | 废弃 | 存在 bug，不可靠 |
| 手动循环（普通） | 使用中 | 可靠，不受长度限制 |
| 手动循环（占位符） | 使用中 | 处理替换文本包含搜索文本的情况 |

---

## 总结

**问题**：`wdReplaceAll` 静默失败（返回 True 但不替换）

**解决方案**：
1. 完全移除 `wdReplaceAll` 依赖
2. 使用手动循环（Delete + InsertAfter）
3. 占位符策略处理特殊情况

**测试**：两种模式均测试通过

**文件**：
- `D:\溯源\backend\app\tools\office\word_win32_tool.py`
- `D:\溯源\backend\test_replace_simple.py`（测试脚本）
- `D:\溯源\backend\test_placeholder_v2.py`（占位符测试）

---

**最终修复完成！** 手动循环方法是最可靠的 Word 替换实现。
