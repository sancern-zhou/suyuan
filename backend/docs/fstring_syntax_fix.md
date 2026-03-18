# 语法错误修复 - f-string 嵌套问题

## ❌ 问题

**错误信息**：
```
SyntaxError: f-string: expressions nested too deeply (assistant_prompt.py, line 202)
```

**原因**：
在 f-string 中直接嵌套 JSON 示例，导致大括号冲突。

**问题代码**：
```python
return f"""
## 输出格式

**示例**：
```json
{
  "thought": "需要读取配置文件",
  "action": {
    "type": "TOOL_CALL",
    "tool": "read_file"
  }
}
```
"""
```

Python 将 JSON 中的 `{` 和 `}` 解析为 f-string 的表达式占位符，导致嵌套过深错误。

---

## ✅ 解决方案

**修复方法**：在 f-string 中，JSON 的大括号需要双写转义。

**修复后代码**：
```python
return f"""
## 输出格式

**示例**：
```json
{{
  "thought": "需要读取配置文件",
  "action": {{
    "type": "TOOL_CALL",
    "tool": "read_file"
  }}
}}
```
"""
```

**规则**：
- f-string 中的 `{` 需要写成 `{{`
- f-string 中的 `}` 需要写成 `}}`

---

## 📝 修改文件

### 1. assistant_prompt.py（第 157-176 行）

**修改前**：
```python
**示例**：
```json
{
  "thought": "需要读取配置文件",
  "reasoning": "用户要求查看配置，应该使用read_file工具",
  "action": {
    "type": "TOOL_CALL",
    "tool": "read_file",
    "args": {
      "path": "D:/config.py"
    }
  }
}
```
```

**修改后**：
```python
**示例**：
```json
{{
  "thought": "需要读取配置文件",
  "reasoning": "用户要求查看配置，应该使用read_file工具",
  "action": {{
    "type": "TOOL_CALL",
    "tool": "read_file",
    "args": {{
      "path": "D:/config.py"
    }}
  }}
}}
```
```

---

### 2. expert_prompt.py（第 85-104 行）

**修改前**：
```python
**示例**：
```json
{
  "thought": "需要获取气象数据",
  "reasoning": "分析污染需要先了解气象条件",
  "action": {
    "type": "TOOL_CALL",
    "tool": "get_weather_data",
    "args": null
  }
}
```
```

**修改后**：
```python
**示例**：
```json
{{
  "thought": "需要获取气象数据",
  "reasoning": "分析污染需要先了解气象条件",
  "action": {{
    "type": "TOOL_CALL",
    "tool": "get_weather_data",
    "args": null
  }}
}}
```
```

---

## ✅ 验证结果

```bash
OK: assistant_prompt length: 4281
OK: expert_prompt length: 2639
OK: assistant_prompt JSON format correct
OK: expert_prompt JSON format correct
```

**验证通过**：
- ✅ 无 SyntaxError
- ✅ 提示词正常构建
- ✅ JSON 示例格式正确
- ✅ 包含正确的 "tool" 字段

---

## 📚 Python f-string 转义规则

### 基本规则

| 字符 | f-string 中写法 | 输出 |
|------|----------------|------|
| `{` | `{{` | `{` |
| `}` | `}}` | `}` |
| `{{` | `{{{{` | `{{` |

### 示例

```python
# ❌ 错误：会被解析为表达式
f"JSON: {\"key\": \"value\"}"  # SyntaxError

# ✅ 正确：双写大括号
f"JSON: {{\"key\": \"value\"}}"  # 输出: JSON: {"key": "value"}

# ✅ 正确：嵌套 JSON
f"""
{{
  "name": "test",
  "data": {{
    "value": 123
  }}
}}
"""
```

---

## 🎯 关键要点

1. **f-string 中的大括号有特殊含义**
   - 单个 `{` 和 `}` 用于表达式插值
   - 需要输出字面大括号时必须双写

2. **JSON 示例在 f-string 中的处理**
   - 所有 `{` 改为 `{{`
   - 所有 `}` 改为 `}}`

3. **验证方法**
   - 导入模块测试是否有 SyntaxError
   - 检查生成的字符串是否包含正确的 JSON 格式

---

## ✅ 修复完成

- ✅ assistant_prompt.py 已修复
- ✅ expert_prompt.py 已修复
- ✅ 语法错误已解决
- ✅ JSON 示例格式正确
- ✅ 系统可正常运行

**问题已完全解决！** ✅
