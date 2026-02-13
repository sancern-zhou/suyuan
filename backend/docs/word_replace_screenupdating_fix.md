# Word 替换功能调试 - 移除ScreenUpdating并添加详细日志

## 问题回顾

**日期**：2026-02-11

**症状**：
- 所有日志显示替换成功（`replacements=1`）
- 文档已保存（`word_document_saved`）
- **但文档内容没有被修改**

**已尝试的修复**：
1. ✅ 设置 `Replacement.Text` - 无效
2. ✅ 清除 `Replacement.ClearFormatting()` - 无效
3. ✅ 使用命名参数 `Execute(FindText=..., ReplaceWith=...)` - 无效
4. ✅ 混合属性设置方式 - 无效

---

## 新的假设

**`ScreenUpdating` 保护可能干扰了替换操作！**

虽然 `ScreenUpdating = False` 通常用于提升性能，但在某些情况下可能会：
- 阻止 Word 更新文档内容
- 导致替换操作执行但没有实际写入文档
- 在保存时丢失所有修改

---

## 修复方案

### 移除 `ScreenUpdating` 保护

**修复前**：
```python
with self.disable_screen_updating():
    find = doc.Content.Find
    find.ClearFormatting()
    find.Replacement.ClearFormatting()
    find.Text = search_text
    find.Replacement.Text = replace_text
    find.Execute(Replace=2)
```

**修复后**：
```python
# ⚠️ 暂时禁用 ScreenUpdating 保护进行测试
# with self.disable_screen_updating():

find = doc.Content.Find
find.ClearFormatting()
find.Replacement.ClearFormatting()
find.Text = search_text
find.Replacement.Text = replace_text
find.Execute(Replace=2)
```

### 添加详细的调试日志

```python
logger.info(
    "word_replace_start",
    path=file_path,
    search_text=search_text,
    search_text_repr=repr(search_text),  # 显示隐藏字符
    search_text_bytes=search_text.encode('utf-8').hex(),  # 十六进制
    replace_text_length=len(replace_text),
    replace_text_preview=replace_text[:100]
)

logger.info(
    "word_replace_formatting_cleared",
    find_object=find,
    replacement_object=find.Replacement
)

logger.info(
    "word_replace_properties_set",
    find_text=find.Text,
    find_text_type=type(find.Text).__name__,
    replacement_text=find.Replacement.Text,
    replacement_text_type=type(find.Replacement.Text).__name__,
    replacement_text_length=len(str(find.Replacement.Text)),
    forward=find.Forward,
    wrap=find.Wrap
)

logger.info(
    "word_replace_executed",
    result=result,
    result_type=type(result).__name__,
    result_value=bool(result) if isinstance(result, (bool, int)) else result
)
```

---

## 新的日志输出

执行替换时会输出详细的调试信息：

```log
word_replace_start
    search_text=数据特征分析：
    search_text_repr='数据特征分析：'
    search_text_bytes=e695b0e68dae9e6b689...  # UTF-8 hex
    replace_text_length=222

word_replace_formatting_cleared
    find_object=<COMObject ...>
    replacement_object=<COMObject ...>

word_replace_properties_set
    find_text=数据特征分析：
    find_text_type=str
    replacement_text=2025年11月3日...
    replacement_text_type=str
    replacement_text_length=222
    forward=True
    wrap=1

word_replace_executed
    result=True
    result_type=bool
    result_value=True
```

---

## 测试验证

运行测试并查看详细日志：

```bash
cd D:\溯源\backend
python test_replace_with_logging.py
```

**检查点**：
1. `search_text_repr` - 确认查找文本正确（无隐藏字符）
2. `replacement_text` - 确认替换文本已设置
3. `replacement_text_length` - 确认长度正确
4. `result` - 确认返回值为 `True`
5. **然后手动检查文档内容是否真的被修改**

---

## 如果仍然无效

如果移除 `ScreenUpdating` 后仍然无效，可能的原因：

### 1. Word 版本兼容性问题
- 某些 Word 版本的 COM 接口可能有问题
- 尝试使用不同的 Word 版本测试

### 2. 文档权限问题
- 文档可能是只读的
- 文档可能被其他程序锁定

### 3. 编码问题
- UTF-8 编码可能导致查找失败
- 尝试使用 ASCII 字符测试

### 4. 最终解决方案
如果所有方法都无效，考虑使用**手动替换**（先删除后插入）：
```python
while find.Execute(FindText=search_text):
    found_range.Delete()
    found_range.InsertAfter(replace_text)
```

---

## 参考资料

- [PyWin32 GitHub Issue #726: Search and replace broken](https://github.com/mhammond/pywin32/issues/726)
- [StackOverflow: Unable to find and replace with win32com](https://stackoverflow.com/questions/57262219/unable-to-find-and-replace-text-with-win32com-client-using-python)
- [Microsoft Learn: Application.ScreenUpdating property](https://learn.microsoft.com/en-us/office/vba/api/word.application.screenupdating)

---

## 总结

**当前假设**：`ScreenUpdating` 保护干扰了替换操作

**修复方案**：
1. 移除 `ScreenUpdating` 保护
2. 添加详细的调试日志
3. 重新测试并检查文档内容

**下一步**：运行测试，查看详细日志，确认替换是否真正生效

---

**测试中...等待结果！**
