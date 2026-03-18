# list_directory 路径引导功能实现总结

## 设计理念

通过**工具返回值自描述**来引导 LLM 理解路径规则，避免膨胀系统提示词。

---

## 修改内容

### 文件：`backend/app/tools/utility/list_directory_tool.py`

#### 1. 修复 working_dir 计算

```python
# 修改前（错误）：
self.working_dir = Path(__file__).parent.parent.parent.parent.parent.parent  # 6个parent

# 修改后（正确）：
self.working_dir = Path(__file__).parent.parent.parent.parent.parent  # 5个parent
# 文件位置：D:\溯源\backend\app\tools\utility\list_directory_tool.py
# parent 1: D:\溯源\backend\app\tools\utility
# parent 2: D:\溯源\backend\app\tools
# parent 3: D:\溯源\backend\app
# parent 4: D:\溯源\backend
# parent 5: D:\溯源\  ✓
```

#### 2. 修改 execute 返回值

添加 `_path_guide` 字段：

```python
return {
    "success": True,
    "data": {
        "entries": entries,
        "count": len(entries),
        "total": total_count,
        "truncated": truncated,
        "path": str(resolved_path),
        # ⭐ 新增：路径引导信息
        "_path_guide": self._build_path_guide(path, resolved_path)
    },
    "summary": self._build_summary(...)
}
```

#### 3. 新增 _build_path_guide 方法

```python
def _build_path_guide(self, input_path: str, resolved_path: Path) -> dict:
    """
    构建路径使用指南（帮助 LLM 理解路径规则）

    功能：
    - 检测路径重复（如"溯源/报告模板"）
    - 提供正确的路径使用示例
    - 明确说明工作目录和路径规则
    """
    # 检测路径重复
    has_duplication = ...
    correct_relative = ...

    # 返回引导信息
    if has_duplication:
        return {
            "working_directory": str(self.working_dir),
            "path_rule": "所有路径都是相对于工作目录的相对路径",
            "your_input": input_path,
            "resolved_to": str(resolved_path),
            "warning": "检测到路径重复：包含工作目录名",
            "suggestion": f"正确路径应为：'{correct_relative}'",
            "correct_usage": [
                f"✓ 相对路径：'{correct_relative}'",
                f"✓ 绝对路径：'D:/溯源/...'",
                f"✗ 错误：'{input_path}'（包含工作目录名）"
            ]
        }
    else:
        return {
            "working_directory": str(self.working_dir),
            "path_rule": "所有路径都是相对于工作目录的相对路径",
            "your_input": input_path,
            "resolved_to": str(resolved_path),
            "status": "path_correct",
            "examples": [
                f"访问子目录：path='{correct_relative}/子目录名'",
                f"访问文件：path='{correct_relative}/文件名.txt'",
                f"返回上级：path='..'"
            ]
        }
```

#### 4. 修改 _create_entry 方法

```python
# 修改前：
rel_path = str(path.relative_to(root))  # 相对于传入路径

# 修改后：
rel_path = str(path.relative_to(self.working_dir)).replace("\\", "/")  # 相对于工作目录

entry = {
    "name": path.name,
    "path": rel_path,  # LLM 可以直接使用这个路径访问文件
    "type": "directory" if path.is_dir() else "file",
    ...
}
```

---

## LLM 学习效果

### 场景1：用户说"查看溯源目录"

**第一次调用**：
```
LLM 调用：list_directory(path="溯源")
系统返回：
{
    "_path_guide": {
        "working_directory": "D:/溯源",
        "your_input": "溯源",
        "resolved_to": "D:/溯源/溯源",
        "warning": "检测到路径重复：包含工作目录名'溯源'",
        "suggestion": "正确路径应为：'.' 或 'D:/溯源/'",
        "correct_usage": [
            "✓ 相对路径：'.'",
            "✓ 绝对路径：'D:/溯源/'",
            "✗ 错误：'溯源'（包含工作目录名）"
        ]
    },
    "entries": [...]
}

LLM 学习：哦！原来"溯源"是工作目录名，我不应该用它作为路径前缀。
```

### 场景2：用户说"查看报告模板目录"

**第二次调用**：
```
LLM 调用：list_directory(path="报告模板")  # ✓ 正确！
系统返回：
{
    "_path_guide": {
        "working_directory": "D:/溯源",
        "your_input": "报告模板",
        "resolved_to": "D:/溯源/报告模板",
        "status": "path_correct",
        "examples": [
            "访问子目录：path='报告模板/子目录名'",
            "访问文件：path='报告模板/文件名.txt'",
            "返回上级：path='..'"
        ]
    },
    "entries": [
        {"name": "images", "path": "报告模板/images"},  # ✓ 相对于工作目录
        {"name": "2025年7月20日臭氧垂直.docx", "path": "报告模板/2025年7月20日臭氧垂直.docx"}
    ]
}

LLM 学习：
1. 路径正确！
2. 返回的 path 字段可以直接用于后续访问
3. 要访问文件，使用 path="报告模板/文件名.docx"
```

### 场景3：用户说"查看文件"

**第三次调用**：
```
LLM 调用：read_file(path="报告模板/2025年7月20日臭氧垂直.docx")  # ✓ 正确！
系统解析：D:\溯源\报告模板\2025年7月20日臭氧垂直.docx  # ✓ 没有重复
结果：成功！✓
```

---

## 关键改进点

### 1. 自描述返回值
- 工具返回值本身包含路径规则说明
- LLM 可以从返回值中学习，不需要外部提示词

### 2. 错误检测与纠正
- 自动检测路径重复（如"溯源/报告模板"）
- 提供明确的修正建议
- 展示正确和错误的用法对比

### 3. 清晰的路径字段
- `path` 字段返回相对于工作目录的路径
- LLM 可以直接使用这个路径访问文件
- 不需要再次拼接或修改

### 4. 实时反馈循环
```
LLM 错误 → 工具警告并纠正 → LLM 学习 → LLM 正确 → 工具确认
```

---

## 对比：修改前 vs 修改后

### 修改前

**LLM 调用**：`list_directory(path="溯源/报告模板")`

**系统返回**：
```json
{
    "entries": [
        {"name": "images", "path": "images"},  // ❌ 相对于传入路径
        {"name": "file.docx", "path": "file.docx"}
    ]
}
```

**LLM 困惑**：
- "images" 是相对于什么的路径？
- 我应该怎么访问它？
- 继续用"溯源/报告模板/images"吗？

### 修改后

**LLM 调用**：`list_directory(path="溯源/报告模板")`

**系统返回**：
```json
{
    "_path_guide": {
        "working_directory": "D:/溯源",
        "your_input": "溯源/报告模板",
        "resolved_to": "D:/溯源/溯源/报告模板",
        "warning": "检测到路径重复：包含工作目录名'溯源'",
        "suggestion": "正确路径应为：'报告模板'",
        "correct_usage": [
            "✓ 相对路径：'报告模板'",
            "✗ 错误：'溯源/报告模板'（包含工作目录名）"
        ]
    },
    "entries": [
        {"name": "images", "path": "溯源/报告模板/images"},  // 相对于工作目录
        {"name": "file.docx", "path": "溯源/报告模板/file.docx"}
    ]
}
```

**LLM 清晰**：
- 哦！我用错路径了
- 正确的路径是"报告模板"
- 下次我会用正确的路径

---

## 推广到其他工具

### 原则
任何返回文件/目录列表的工具都应该：
1. 添加 `_path_guide` 字段说明路径规则
2. 返回的 `path` 字段应该是相对于工作目录的路径
3. 检测常见错误并提供纠正建议

### 需要修改的工具
- `search_files` (glob_tool.py)
- `grep` (grep_tool.py)
- 其他返回文件列表的工具

### 统一模式
```python
return {
    "success": True,
    "data": {
        "results": [...],
        # ⭐ 添加路径引导
        "_path_guide": {
            "working_directory": str(self.working_dir),
            "path_note": "所有路径都是相对于工作目录的相对路径"
        }
    }
}
```

---

## 总结

### 核心思想
**让工具返回值自描述**，通过工具本身引导 LLM 理解路径规则，而不是依赖外部提示词。

### 优势
1. ✅ 避免系统提示词膨胀
2. ✅ 上下文相关（每次调用都提供当前路径信息）
3. ✅ 错误检测与纠正（实时反馈）
4. ✅ 学习能力强（LLM 从返回值中学习）

### 效果
- **第一次错误**：工具检测并提示
- **第二次学习**：LLM 理解规则
- **第三次正确**：LLM 应用学习

这就是"从错误中学习"的设计模式！
