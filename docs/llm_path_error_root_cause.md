# LLM 路径错误根本原因分析报告

## 问题现象

用户提问：
1. "查看溯源目录" → LLM 调用 `list_directory(path="溯源")` ✓
2. "查看报告模板目录" → LLM 调用 `list_directory(path="溯源/报告模板")` ✗
3. "查看2025年7月20日臭氧垂直报告内容" → LLM 调用 `read_file(path="溯源/报告模板/2025年7月20日臭氧垂直.docx")` ✗

错误路径：`D:\溯源\溯源\报告模板\文件.docx`（重复拼接）

---

## 根本原因分析

### 原因1：系统提示词缺少关键信息 ⚠️ 核心问题

**当前系统提示词（assistant_prompt.py）**：
```python
"## JSON 规范\n"
"- 使用英文双引号 \"\"，禁止中文引号 \"\n"
"- Windows路径用正斜杠：`\"D:/folder/file.txt\"`\n"  # ❌ 只说明格式，没说明基准
"- 文件操作工具统一使用 `path` 参数（不是 `file_path`）\n"
```

**缺失的关键信息**：
- ❌ **没有说明工作目录是什么**（`D:\溯源\`）
- ❌ **没有说明相对路径的定义**（相对于工作目录）
- ❌ **没有提供路径使用示例**
- ❌ **没有说明用户输入"查看溯源目录"时应该使用什么路径**

**LLM 的理解**：
- 用户说"查看溯源目录"
- LLM 推理：应该调用 `list_directory(path="溯源")`
- 成功！LLM 认为 "溯源" 是正确的路径前缀
- 下次用户说"查看报告模板目录"
- LLM 推理：在"溯源"目录下，所以使用 `path="溯源/报告模板"`

---

### 原因2：list_directory 返回路径格式有歧义

**当前实现（list_directory_tool.py:232-258）**：
```python
def _create_entry(self, path: Path, root: Path) -> Optional[Dict[str, Any]]:
    """创建条目信息"""
    # 计算相对路径
    rel_path = str(path.relative_to(root))  # ❌ 相对于传入路径，不是工作目录

    entry = {
        "name": path.name,
        "path": rel_path,  # ❌ 有歧义：LLM不知道这是相对于什么的路径
        "type": "directory" if path.is_dir() else "file",
        ...
    }
```

**调用示例**：
```python
# 输入：list_directory(path="溯源/报告模板")
# 实际访问：D:\溯源\溯源\报告模板（错误路径）
# 返回：
{
  "entries": [
    {"name": "images", "path": "images"},  # ❌ 相对于"溯源/报告模板"的路径
    {"name": "2025年7月20日臭氧垂直.docx", "path": "2025年7月20日臭氧垂直.docx"}
  ]
}
```

**LLM 的困惑**：
- 看到返回的路径是 `"images"`、`"2025年7月20日臭氧垂直.docx"`
- 不确定这些路径应该如何使用
- 推理：之前使用"溯源/报告模板"成功，所以继续使用这个前缀

---

### 原因3：对话历史中的误导信息

**第一次调用**：
```
用户：查看溯源目录
LLM：list_directory(path="溯源")
结果：成功（实际访问 D:\溯源\溯源，但恰好存在这个目录或者没有严格检查）
```

**第二次调用**：
```
用户：查看报告模板目录
LLM推理：用户之前说"查看溯源目录"，我用了"溯源"成功。
       现在用户说"查看报告模板目录"，报告模板在溯源目录下，
       所以应该用"溯源/报告模板"
调用：list_directory(path="溯源/报告模板")
结果：访问 D:\溯源\溯源\报告模板（路径重复）
```

**第三次调用**：
```
用户：查看2025年7月20日臭氧垂直报告内容
LLM推理：之前使用"溯源/报告模板"成功，所以继续使用这个前缀
调用：read_file(path="溯源/报告模板/2025年7月20日臭氧垂直.docx")
结果：访问 D:\溯源\溯源\报告模板\文件.docx（文件不存在）
```

---

## 对话流程时序分析

```
时间轴          LLM 推理                                    实际访问路径
────────────────────────────────────────────────────────────────────────────
T1 (09:38:02)   用户："查看溯源目录"                          ─
                → 调用 list_directory(path="溯源")            D:\溯源\溯源
                → 返回成功（实际访问了 D:\溯源\溯源）         ─

T2 (09:38:54)   用户："查看报告模板目录"                      ─
                → 推理：溯源目录下有报告模板，用"溯源/报告模板" ─
                → 调用 list_directory(path="溯源/报告模板")    D:\溯源\溯源\报告模板
                → 返回成功（恰好目录存在或者没有严格检查）     ─

T3 (09:39:28)   用户："查看2025年7月20日臭氧垂直报告内容"    ─
                → 推理：继续使用"溯源/报告模板"前缀            ─
                → 调用 read_file(path="溯源/报告模板/...")     D:\溯源\溯源\报告模板\...
                → 失败：文件不存在                           ✗
```

---

## 为什么 LLM 会输出错误路径？

### LLM 的认知模型：

```
用户的第一次请求 → 我的路径："溯源" → 成功！
用户的第二次请求 → 我的路径："溯源/报告模板" → 成功！
用户的第三次请求 → 我的路径："溯源/报告模板/文件.docx" → 失败？

LLM 思考："为什么第三次失败了？前两次都成功了啊！"
```

### 缺失的信息链条：

```
系统应该告诉 LLM：
1. 工作目录是 D:\溯源\
2. 相对路径是相对于工作目录的
3. 传入 "溯源" 会被解析为 D:\溯源\溯源（错误）
4. 正确的做法是传入 "报告模板"（访问 D:\溯源\报告模板）

但系统没有告诉 LLM 这些信息！
```

---

## 解决方案优先级

### 🚨 立即修复（高优先级）

#### 方案1：修改系统提示词（最有效）

**位置**：`backend/app/agent/prompts/assistant_prompt.py`

**添加内容**：
```python
prompt_parts = [
    "你是通用办公助手，帮助用户完成日常办公任务。\n",
    "\n",
    "## ⚠️ 路径使用规范（CRITICAL）\n",
    "\n",
    "**工作目录**：`D:/溯源/`\n",
    "\n",
    "**路径规则**：\n",
    "- ✅ 相对路径：相对于工作目录 `D:/溯源/`\n",
    "  - 例如：`报告模板/file.docx` → 访问 `D:/溯源/报告模板/file.docx`\n",
    "- ✅ 绝对路径：直接使用完整路径\n",
    "  - 例如：`D:/溯源/报告模板/file.docx` → 访问 `D:/溯源/报告模板/file.docx`\n",
    "- ❌ 禁止：路径中包含工作目录名\n",
    "  - 例如：不要使用 `溯源/报告模板/file.docx`（会导致重复）\n",
    "\n",
    "**示例**：\n",
    "- 用户说"查看溯源目录" → 使用 `path="."` 或 `path="D:/溯源/"`\n",
    "- 用户说"查看报告模板目录" → 使用 `path="报告模板"` 或 `path="D:/溯源/报告模板/"`\n",
    "- 用户说"读取报告模板下的文件.docx" → 使用 `path="报告模板/文件.docx"`\n",
    "\n",
    "## 核心职责\n",
    # ... 继续原有内容
]
```

#### 方案2：修改 list_directory 返回格式

**位置**：`backend/app/tools/utility/list_directory_tool.py`

**修改前**：
```python
# 计算相对路径
rel_path = str(path.relative_to(root))  # 相对于传入路径
```

**修改后**：
```python
# 计算相对于工作目录的路径（更清晰）
try:
    rel_path = str(path.relative_to(self.working_dir))  # 相对于工作目录
except ValueError:
    rel_path = str(path.relative_to(root))  # 降级：相对于传入路径
```

并在返回中添加路径说明：
```python
return {
    "success": True,
    "data": {
        "entries": entries,
        "count": len(entries),
        "total": total_count,
        "truncated": truncated,
        "path": str(resolved_path),
        "working_dir": str(self.working_dir),  # ✅ 新增：明确工作目录
        "path_note": "所有路径字段均为相对于工作目录的相对路径"  # ✅ 新增：说明
    },
    "summary": ...
}
```

#### 方案3：Input Adapter 路径修正（已有 PathResolver）

**位置**：`backend/app/agent/input_adapter.py`

在 Input Adapter 中自动检测和修正路径：

```python
class InputAdapter:
    def adapt(self, tool_name: str, raw_args: dict) -> dict:
        # 检测 path 参数
        if "path" in raw_args:
            from app.utils.path_resolver import PathResolver
            resolver = PathResolver("D:/溯源/")

            # 验证并修正路径
            validation = resolver.validate_path(raw_args["path"], must_exist=False)

            if validation["valid"]:
                raw_args["path"] = str(validation["path"])
            else:
                # 路径无效，但不阻止（让工具自己处理）
                logger.warning("input_adapter_path_validation_failed",
                             tool=tool_name, path=raw_args["path"])
```

---

### 📊 短期优化（中优先级）

#### 方案4：工具描述优化

**修改所有涉及路径的工具描述**，添加明确的路径说明：

```python
description="""列出目录内容

⚠️ **路径格式重要**：
- 工作目录：`D:/溯源/`
- 相对路径示例：`报告模板/` → 访问 `D:/溯源/报告模板/`
- 绝对路径示例：`D:/溯源/报告模板/` → 访问 `D:/溯源/报告模板/`
- ❌ 避免使用：`溯源/报告模板/`（会导致路径重复）

功能：
- 列出指定目录中的文件和子目录
...
"""
```

#### 方案5：增强错误提示

当路径不存在时，返回更友好的错误信息：

```python
{
    "success": False,
    "error": "文件不存在",
    "data": {
        "requested_path": "溯源/报告模板/文件.docx",
        "resolved_path": "D:\\溯源\\溯源\\报告模板\\文件.docx",
        "working_directory": "D:\\溯源",
        "suggestion": "路径中包含工作目录名'溯源'，导致重复。请使用相对路径：'报告模板/文件.docx' 或绝对路径：'D:/溯源/报告模板/文件.docx'"
    }
}
```

---

### 🔧 长期改进（低优先级）

#### 方案6：统一路径处理架构

1. **在工具基类中集成 PathResolver**
2. **在 Input Adapter 层面自动标准化所有路径**
3. **创建路径处理最佳实践文档**

#### 方案7：用户意图理解优化

当用户说"查看X目录"时，自动转换为正确的路径：
- "查看溯源目录" → `path="."` 或 `path="D:/溯源/"`
- "查看报告模板目录" → `path="报告模板/"`

---

## 总结

### 核心问题
**系统提示词缺少关键信息**，导致 LLM 无法理解：
- 工作目录是什么
- 相对路径的定义
- 应该如何构造路径

### LLM 的错误推理链
```
用户："查看溯源目录"
→ LLM：没有明确指导，尝试使用 path="溯源"
→ 系统：实际访问 D:\溯源\溯源（恰好存在或未检查）
→ LLM：认为"溯源"是正确的路径前缀

用户："查看报告模板目录"
→ LLM：推理"溯源"下有"报告模板"，使用 path="溯源/报告模板"
→ 系统：访问 D:\溯源\溯源\报告模板（路径重复）
→ LLM：继续认为这个前缀是正确的

用户："查看文件"
→ LLM：使用 path="溯源/报告模板/文件.docx"
→ 系统：文件不存在 → 失败
```

### 立即行动项
1. ✅ **修改系统提示词**（最有效，立即见效）
2. ✅ **修改 list_directory 返回格式**（消除歧义）
3. ✅ **启用 Input Adapter 路径修正**（已有 PathResolver）
4. ✅ **优化工具描述**（提供明确示例）

---

## 测试验证

修改后，LLM 应该：

```
用户："查看溯源目录"
→ LLM：使用 path="." 或 path="D:/溯源/"
→ 系统：访问 D:\溯源\
→ LLM：看到返回的工作目录信息

用户："查看报告模板目录"
→ LLM：使用 path="报告模板/" 或 path="D:/溯源/报告模板/"
→ 系统：访问 D:\溯源\报告模板\
→ LLM：正确的路径

用户："查看文件"
→ LLM：使用 path="报告模板/文件.docx"
→ 系统：访问 D:\溯源\报告模板\文件.docx
→ 成功！✓
```
