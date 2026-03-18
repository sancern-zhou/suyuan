# 简化方案：只依赖 list_directory 的 _path_guide

## 设计原则

**简单优先，避免过度工程化**

---

## 删除的文件

- ✅ `backend/app/utils/path_resolver.py` - 已删除（过度工程化）

---

## 简化后的方案

### 核心机制：list_directory 的 _path_guide

**工作原理**：
1. LLM 调用 `list_directory(path="溯源/报告模板")`
2. 工具检测路径重复，返回警告和建议
3. LLM 从返回值中学习，下次使用正确路径

**示例返回**：
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
      "✓ 绝对路径：'D:/溯源/报告模板'",
      "✗ 错误：'溯源/报告模板'（包含工作目录名）"
    ]
  },
  "entries": [
    {"name": "images", "path": "溯源/报告模板/images"},
    {"name": "file.docx", "path": "溯源/报告模板/file.docx"}
  ]
}
```

### LLM 学习流程

```
第1轮：LLM 输入 "溯源/报告模板"
├─ 系统返回：warning + suggestion
└─ LLM 学习："溯源"是工作目录名，不应该使用

第2轮：LLM 输入 "报告模板"
├─ 系统返回：status: "path_correct"
└─ LLM 确认：路径正确！

第3轮：LLM 输入 "报告模板/file.docx"
└─ 成功！
```

---

## 工具简化

### unpack_office 简化前后对比

**简化前（过度工程化）**：
```python
# 引入 PathResolver
from app.utils.path_resolver import PathResolver

def __init__(self):
    self.path_resolver = PathResolver(self.working_dir)

async def execute(self, path: str, **kwargs):
    # 使用 PathResolver
    file_path = self.path_resolver.resolve(path, must_exist=True)
    if file_path is None:
        validation = self.path_resolver.validate_path(...)
        ...
```

**简化后**：
```python
# 直接使用 pathlib
from pathlib import Path

async def execute(self, path: str, **kwargs):
    # 简单的路径处理
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = self.working_dir / file_path
    file_path = file_path.resolve()

    # 检查文件是否存在
    if not file_path.exists():
        return {"success": False, "error": "文件不存在"}
```

**代码减少**：~40行 → ~10行

---

## 优势

1. ✅ **简单**：不引入额外的抽象层
2. ✅ **直观**：所有工具使用相同的简单路径处理
3. ✅ **易懂**：新开发者容易理解
4. ✅ **够用**：LLM 可以通过 `_path_guide` 学习正确路径

---

## 适用场景

**适合**：
- LLM 需要从工具返回值中学习路径规则
- 不需要频繁修改工具代码
- 希望保持代码简单

**不适合**：
- 需要所有工具都有自动路径修正（目前只有 list_directory 有提示）
- LLM 经常忽略警告（但可以通过更好的提示词解决）

---

## 修改总结

| 文件 | 操作 |
|------|------|
| `backend/app/utils/path_resolver.py` | ❌ 删除 |
| `backend/app/tools/office/unpack_tool.py` | ✅ 简化，移除 PathResolver |
| `backend/app/tools/utility/list_directory_tool.py` | ✅ 保留 `_path_guide` |

**核心思想**：让工具返回值自描述，LLM 从中学习，而不是通过复杂的路径解析层。

---

## 工作目录配置

所有工具使用动态工作目录：
```python
self.working_dir = Path.cwd().parent  # 动态获取：D:\溯源\ 或 /opt/app/ 等
```

**优点**：
- ✅ 支持任意部署路径
- ✅ 不需要配置文件
- ✅ 不需要环境变量

**假设**：
- 后端从 `backend/` 目录启动
- 项目根目录是 `backend/` 的父目录

---

## 总结

**简化方案的核心**：
1. 删除 PathResolver（避免过度工程化）
2. 只在 list_directory 中提供 `_path_guide`
3. LLM 从工具返回值中学习正确路径
4. 其他工具使用简单的 pathlib 路径处理

**效果**：
- 代码更简单
- 更易维护
- 仍然能解决问题（LLM 学习机制）
