# unpack_office 工具问题 - 最终诊断报告

**日期**: 2026-02-22
**问题**: `unpack_office` 工具在后端启动时导入失败

---

## 🔍 日志分析摘要

### 关键错误（第151行）
```
2026-02-22 11:12:44 [warning] tool_import_failed
error=No module named 'openpyxl' tool=unpack_office
```

### 实际情况
- **global_tool_registry**: 只注册了 60 个工具（缺少 `unpack_office`）
- **Agent 实例**: 每个只有 58 个工具
- **refresh_tools 机制**: ✅ 正常工作（第273-324行有完整日志）
- **根本原因**: ❌ 依赖缺失导致工具导入失败

---

## 📊 问题链条

### 1. 导入依赖链
```
app/tools/__init__.py:442
  from app.tools.office.unpack_tool import UnpackOfficeTool
    ↓
  app/tools/office/__init__.py (模块初始化)
    from .excel_recalc_tool import ExcelRecalcTool  # 第36行
      ↓
    excel_recalc_tool.py:20
      from openpyxl import load_workbook
        ↓
      ❌ ModuleNotFoundError: No module named 'openpyxl'
```

### 2. 级联失败
1. `openpyxl` 未安装
2. → `excel_recalc_tool.py` 导入失败
3. → `app/tools/office/__init__.py` 初始化失败
4. → `UnpackOfficeTool` 导入失败（连带 `ExcelRecalcTool`, `AddSlideTool`）
5. → 工具注册失败（被 try-except 捕获，记录警告）

### 3. 受影响的工具（3个）
- ❌ `unpack_office` - Office 文件解包
- ❌ `recalc_excel` - Excel 公式重算
- ❌ `add_ppt_slide` - PPT 幻灯片添加

---

## ✅ 解决方案

### 步骤 1: 安装缺失依赖

```bash
# 激活虚拟环境
conda activate suyuan

# 安装 openpyxl
pip install openpyxl>=3.1.0

# 验证安装
python -c "import openpyxl; print(f'openpyxl version: {openpyxl.__version__}')"
```

### 步骤 2: 重启后端

```bash
cd D:\溯源\backend

# 清理 Python 缓存（可选但推荐）
python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"

# 重启后端
python -m uvicorn app.main:app --reload
```

### 步骤 3: 验证修复

启动后检查日志，应该看到：

```
[info] tool_registered ... tool=unpack_office
[info] tool_loaded tool=unpack_office
[info] tool_registered ... tool=recalc_excel
[info] tool_loaded tool=recalc_excel
[info] tool_registered ... tool=add_ppt_slide
[info] tool_loaded tool=add_ppt_slide
...
[info] agent_instances_created
  multi_expert_tools=61  # 应该从 58 增加到 61
  meteorology_expert_tools=61
  ...
[info] refreshing_global_agent_tools
[info] global_agents_refreshed
  multi_expert_tools=61  # 刷新后仍然是 61
```

---

## 📝 代码修改记录

### 1. 更新 requirements.txt

**文件**: `backend/requirements.txt`

**修改**:
```diff
  # Report Export (PDF/Word generation)
  weasyprint==63.1
  python-docx==1.1.2
+ openpyxl>=3.1.0  # Excel file manipulation for Office tools
  markdown==3.7
  jinja2==3.1.4
```

### 2. 已完成的修复（上一轮）

以下修复在本次问题中**已正常工作**：

- ✅ `app/main.py`: 添加了 `refresh_tools()` 调用（第273行日志证实）
- ✅ `app/agent/core/executor.py`: 添加了 `refresh_tools()` 方法
- ✅ `app/agent/react_agent.py`: 添加了 `refresh_tools()` 接口
- ✅ `app/agent/core/planner.py`: 修复了使用全局单例

**日志证据**（第273-324行）:
```
refreshing_global_agent_tools
refreshing_tool_registry
builtin_tools_registered ... has_unpack_office=False  # 因为源头就没有
agent_tools_refreshed ... tool_count=58
...
global_agents_refreshed ... multi_expert_tools=58
```

---

## 🎯 总结

### 之前的误判
我们最初认为问题是 Agent 刷新机制不工作，因此添加了 `refresh_tools()` 功能。

### 真正的问题
问题其实是**依赖缺失**导致工具无法导入到 `global_tool_registry`。即使刷新机制工作正常，也只是"刷新了空气"（刷新了一个本就缺少工具的注册表）。

### 最终修复
1. ✅ 添加了 `openpyxl` 依赖到 `requirements.txt`
2. ✅ 保留了 `refresh_tools()` 机制（对未来动态工具加载有益）

### 预期结果
安装依赖后重启，所有 Agent 实例将有 **61 个工具**（包含 `unpack_office`, `recalc_excel`, `add_ppt_slide`）。

---

**相关文件**:
- 日志文件: `D:\溯源\docs\后端日志.md`
- 修复记录: `D:\溯源\backend\docs\unpack_office_fix_report.md`
- 诊断脚本: `D:\溯源\final_diagnosis.py`
