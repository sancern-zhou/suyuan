# JSON修复功能集成说明

## 问题描述

LLM生成的JSON响应包含未转义的特殊字符，导致标准JSON解析器失败：

1. **未转义的反斜杠**：Windows路径如 `D:\溯源` 中的 `\溯` 不是有效的JSON转义序列
2. **未转义的双引号**：字符串值内部的双引号（如文件名 `"2025年臭氧垂直报告7-ok - 副本.docx"`）没有被转义

### 错误示例
```json
{
  "thought": "用户需要在当前工作目录D:\溯源中搜索文件"test.docx"。"
}
```

**解析失败位置**：第29个字符 `\溯` - `Invalid \escape`

## 解决方案

集成 `json-repair` 库来自动修复LLM生成的格式错误的JSON。

### 安装

```bash
pip install json-repair
```

### 实现细节

**文件**: `app/utils/llm_response_parser.py`

1. **导入json-repair库**：
   ```python
   from json_repair import repair_json
   ```

2. **在解析流程中添加修复步骤**：
   - 在 `parse()` 方法中，作为第一步执行
   - 在所有其他解析策略之前
   - 自动检测并修复常见问题

3. **修复功能** (`_repair_json_with_library`)：
   - 使用 `repair_json()` 修复JSON
   - 验证修复后的JSON是否可解析
   - 记录修复统计信息
   - 失败时回退到原内容

### 修复的问题

json-repair库可以自动处理：

- ✅ 未转义的反斜杠（Windows路径等）
- ✅ 未转义的双引号
- ✅ 缺失的括号
- ✅ 尾部的额外内容
- ✅ 其他格式问题

## 测试

**测试文件**: `tests/test_json_repair_integration.py`

运行测试：
```bash
cd backend
python tests/test_json_repair_integration.py
```

### 测试用例

1. **未转义的Windows路径和引号**
   - 输入: `D:\溯源` 和 `"文件名.docx"`
   - 结果: ✅ 自动修复并成功解析

2. **已正确转义的JSON**
   - 结果: ✅ 保持不变，正常解析

3. **普通JSON（无路径问题）**
   - 结果: ✅ 正常解析

## 日志示例

```
[info     ] json_repair_successful         original_length=299 repaired_length=661
[info     ] json_repair_valid              message=修复后的JSON可以成功解析
[info     ] response_parsed_directly       keys=['thought', 'reasoning', 'action']
```

## 统计信息

解析器会记录JSON修复的次数：

```python
{
    "total_attempts": 3,
    "json_repair": 3,      # JSON修复次数
    "direct_json": 3,      # 直接JSON解析成功次数
    ...
}
```

## 性能影响

- **开销**: 最小（仅在需要时调用）
- **成功率**: 显著提高（从失败到成功）
- **兼容性**: 完全向后兼容（如果json-repair不可用，自动跳过）

## 最佳实践

1. **依赖管理**: 将 `json-repair` 添加到 `requirements.txt`
2. **错误处理**: 如果json-repair失败，自动回退到原内容
3. **日志记录**: 记录所有修复操作，便于调试
4. **统计监控**: 跟踪修复频率，评估LLM输出质量

## 相关资源

- [json-repair GitHub](https://github.com/mangiucugna/json_repair)
- [json-repair PyPI](https://pypi.org/project/json-repair/)
- [教程: 使用json_repair修复LLM输出](https://medium.com/@yanxingyang/tutorial-on-using-json-repair-in-python-easily-fix-invalid-json-returned-by-llm-8e43e6c01fa0)

## 更新日期

2026-02-08
