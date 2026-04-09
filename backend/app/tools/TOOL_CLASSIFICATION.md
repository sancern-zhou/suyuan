# 工具分类规范（基于现有 LLMTool 架构）

## 核心原则

利用现有 `LLMTool` 基类的 `requires_context` 标志区分工具类型，**不创建新的子类**。

---

## 分类标准

### 1. 数据分析工具

**特征**：
- 处理大量数据（数千至数万条记录）
- 需要数据外部化存储（避免 LLM 看到大数据）
- 需要 data_id 引用机制
- 需要类型化数据加载（Pydantic 模型）

**架构要求**：
- ✅ `requires_context=True`（必须）
- ✅ 签名：`async def execute(self, context: ExecutionContext, **kwargs)`
- ✅ 必须返回 UDF v2.0 格式
- ✅ 使用 `context.save_data()` 外部化大数据

**工具列表**：
- `get_vocs_data` - VOCs 数据查询
- `get_pm25_ionic` - 颗粒物离子组分
- `get_pm25_carbon` - 颗粒物碳组分
- `get_pm25_crustal` - 颗粒物地壳元素
- `get_pm25_trace` - 颗粒物微量元素
- `calculate_pmf` - PMF 源解析
- `calculate_obm_ofp` - OBM/OFP 分析
- `calculate_soluble` - 水溶性离子分析
- `calculate_carbon` - 碳组分分析
- `calculate_crustal` - 地壳元素分析
- `calculate_trace` - 微量元素分析
- `calculate_reconstruction` - 质量重构
- `smart_chart_generator` - 智能图表生成
- `get_weather_data` - 气象数据查询
- `get_backward_trajectory` - 后向轨迹
- `analyze_upwind_enterprises` - 上风向企业分析

**代码示例**：
```python
class GetVOCsDataTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="get_vocs_data",
            description="查询VOCs组分数据",
            category=ToolCategory.QUERY,
            requires_context=True  # ✅ 关键标志
        )

    async def execute(
        self,
        context: ExecutionContext,  # ✅ 第一个参数
        station: str,
        start_time: str,
        end_time: str
    ) -> Dict[str, Any]:
        # 查询数据
        data = await query_vocs(...)

        # 外部化存储
        data_id = context.save_data(data, schema="vocs_unified")

        # 返回 UDF v2.0
        return {
            "status": "success",
            "data": data[:24],  # 预览
            "data_id": data_id,  # 完整数据引用
            "metadata": {"schema_version": "v2.0", ...},
            "summary": "..."
        }
```

---

### 2. 办公助手工具

**特征**：
- 处理文件、文档、系统命令
- 输入输出简单明确
- 不涉及大数据集

**架构要求**：
- ❌ `requires_context=False`（默认）
- ✅ 签名：`async def execute(self, **kwargs)`（无需 context）
- ✅ 返回简单字典：`{success, data, summary}`

**工具列表**：
- `bash` - 执行 Shell 命令
- `read_file` - 读取文件/目录
- `write_file` - 写入文件
- `analyze_image` - 图片分析（OCR/理解）
- `word_processor` - Word 文档处理
- `execute_python` - Python代码执行（Excel/数据分析/可视化）
- `create_scheduled_task` - 创建定时任务

**代码示例**：
```python
class ReadFileTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="read_file",
            description="读取文件",
            category=ToolCategory.OFFICE,
            requires_context=False  # ✅ 不需要 context
        )

    async def execute(self, path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        content = read_file_content(path, encoding)

        return {
            "success": True,
            "data": {"path": path, "content": content},
            "summary": f"成功读取：{path}"
        }
```

---

### 3. 任务管理工具

**特征**：
- 管理任务清单
- 只需要 TaskList 依赖
- 不涉及数据管理

**架构要求**：
- ⚠️ `requires_context=False`（不需要完整 ExecutionContext）
- ✅ 添加 `requires_task_list=True` 属性
- ✅ 签名：`async def execute(self, task_list: TaskList, **kwargs)`
- ❌ **不支持 activeForm 参数**（项目不需要）

**工具列表**：
- `create_task` - 创建任务
- `update_task` - 更新任务状态
- `get_task` - 获取任务详情
- `list_tasks` - 列出任务清单

**代码示例**：
```python
class CreateTaskTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="create_task",
            description="创建任务",
            category=ToolCategory.TASK_MANAGEMENT,
            requires_context=False  # ✅ 不需要 ExecutionContext
        )
        self.requires_task_list = True  # ✅ 需要 TaskList

    async def execute(
        self,
        task_list: TaskList,  # ✅ 第一个参数
        subject: str,
        description: str
        # ❌ 移除 activeForm 参数
    ) -> Dict[str, Any]:
        task = task_list.create_task(...)
        return {
            "status": "success",
            "data": {"task_id": task.id, ...},
            "summary": "..."
        }
```

---

## 重构检查清单

### ❌ 要删除的内容
- [ ] 所有任务管理工具中的 `activeForm` 参数
- [ ] 提示词中的 `activeForm` 参数说明
- [ ] `tool_adapter.py` 中的硬编码工具名单（TOOLS_NEEDING_DATA_CONTEXT、TASK_MANAGEMENT_TOOLS）

### ✅ 要保留的内容
- [x] 现有 `LLMTool` 基类
- [x] `requires_context` 标志机制
- [x] Context-Aware V2 规范（仅用于数据分析工具）
- [x] UDF v2.0 格式（仅用于数据分析工具）

### 🔧 要简化的内容
- [ ] `tool_adapter.py` 注入逻辑：基于工具属性动态判断，不用硬编码工具名
- [ ] 提示词：统一参数命名为 snake_case（task_id 而非 taskId）
