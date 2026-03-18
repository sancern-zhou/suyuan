# Mini-Agent 对比与落地方案

## 一、差异概述（基于源码）

| 维度 | Mini-Agent | 现有溯源 Agent | 主要差异 |
| --- | --- | --- | --- |
| 入口架构 | mini_agent/agent.py 单一 Agent，构造时注入 LLM/工具/workspace，un() 内统一循环和日志 | ackend/app/agent/react_agent.py + expert_router_v3.py，入口分散在 SSE/CLI，Prompt/上下文/日志分别在不同模块 | 缺少统一的 Agent 外壳和 run log，导致上下文和日志管理割裂 |
| 上下文与记忆 | _estimate_tokens、_summarize_messages 在 Agent 内实现；SessionNoteTool 主动记录/回忆笔记 (mini_agent/tools/note_tool.py) | 有 Working/Session/LongTerm memory，但无主动记笔记、无统一上下文摘要逻辑 | 容易出现 token 超限和重要事实丢失 |
| 技能/工具管理 | skill_loader.py、mcp_loader.py 统一管理技能包，工具加载集中化 | 各 Executor 在 _load_tools 内自行 import，	ool_adapter 只是包装已有工具 | 难以扩展和维护，出现 	ool_not_in_registry、input_bindings_not_found |
| 日志 | AgentLogger 把每次请求、响应、工具执行写入 ~/.mini-agent/log/agent_run_x.log | 日志散落在 structlog 中，需翻大日志定位问题 | 缺少单次任务的完整 run log |

---

## 二、核心目标

1. 构建统一 AgentShell，集中处理 System Prompt、Workspace、Token 控制和 run log。
2. 引入 Session Note 工具，结合自动摘要，提供主动记忆能力。
3. 用 SkillRegistry 统一管理工具/技能，完善依赖图，消除注册缺失。
4. 输出独立的 run log 文件，打通 SSE 与本地日志的可观测性。

---

## 三、实施方案（源码级步骤）

### 3.1 AgentShell：复用 Mini-Agent 架构

1. **新建 ackend/app/agent/agent_shell.py**
   ``python
   class AgentShell:
       def __init__(self, llm_client, tools: list[Tool], workspace_dir: str, token_limit: int):
           self.llm = llm_client
           self.tools = {tool.name: tool for tool in tools}
           self.workspace_dir = Path(workspace_dir)
           self.workspace_dir.mkdir(parents=True, exist_ok=True)
           self.token_limit = token_limit
           self.messages = [Message(role="system", content=self._inject_workspace_prompt())]
           self.logger = RunLogger()
           self.api_total_tokens = 0
           self._skip_next_token_check = False
   ``
   - _inject_workspace_prompt() 参考 mini_agent/agent.py:63-69，把当前 workspace 信息附加到 system prompt。

2. **移植 token 控制逻辑**
   - 从 mini_agent/agent.py:82-219 拆出 _estimate_tokens、_summarize_messages、_create_summary。
   - _create_summary 改为调用我们已有的 LLMPlanner.llm_client.generate(...)，在摘要前通过 Session Note 工具记录关键信息。

3. **重构 ReActAgent.analyze**
   - 在 ackend/app/agent/react_agent.py:131-270 中：
     ``python
     shell = AgentShell(
         llm_client=self.planner.llm_client,
         tools=list(self.executor.tool_registry.values()),
         workspace_dir=f"./workspace/{actual_session_id}",
         token_limit=self.working_context_limit,
     )
     ``
   - 在 SSE 的 event_generator 中调用 wait shell.summarize_if_needed()，并把 event 写入 shell.messages。
   - Pipeline 完成后，通过 SSE “complete” 事件返回 shell.logger.get_log_path()。

### 3.2 Session Note 工具：主动记忆

1. **新建 ackend/app/tools/session_note.py**
   - 复制 mini_agent/tools/note_tool.py:17-199，存储路径改为 Path(f"./tmp/{session_id}/.agent_notes.json")。
   - 将返回类型适配我们的工具格式，例如：
     ``python
     return {
         "status": "success",
         "data": note,
         "summary": f"Recorded note: {content}"
     }
     ``

2. **注册工具**
   - 在 ackend/app/agent/tool_adapter.py:get_react_agent_tool_registry 中：
     ``python
     from app.tools.session_note import SessionNoteTool, RecallNoteTool
     tool_registry["record_note"] = SessionNoteTool(memory_file=note_path).execute
     tool_registry["recall_notes"] = RecallNoteTool(memory_file=note_path).execute
     ``
   - 
ote_path 可通过 ExecutionContext 传递 session_id。

3. **在各专家中使用**
   - 更新气象/组件/报告专家提示词，明确“识别到关键结果必须调用 record_note”。
   - 报告专家在生成最终 Markdown 前调用 ecall_notes，把结果放入 LLM 提示。

4. **Session 生命周期**
   - 当 ReActAgent._get_or_create_session 重置会话时，清理对应的笔记文件。

### 3.3 SkillRegistry：统一工具加载

1. **新建 ackend/app/agent/tools/skill_registry.py**
   ``python
   class Skill:
       name: str
       def load_tools(self) -> dict[str, Tool]:
           raise NotImplementedError

   class SkillRegistry:
       def __init__(self):
           self.skills = {}
       def register(self, skill: Skill):
           self.skills[skill.name] = skill
       def load(self, skill_name: str) -> dict[str, Tool]:
           return self.skills[skill_name].load_tools()
   skill_registry = SkillRegistry()
   ``

2. **实现技能**（示例）
   ``python
   class MeteorologySkill(Skill):
       name = "meteorology"
       def load_tools(self):
           from app.tools.query.get_weather_data.tool import GetWeatherDataTool
           from app.tools.analysis.meteorological_trajectory_analysis.tool import MeteorologicalTrajectoryAnalysisTool
           ...
           return {
               "get_weather_data": GetWeatherDataTool(),
               "meteorological_trajectory_analysis": MeteorologicalTrajectoryAnalysisTool(),
               ...
           }
   ``
   - 组件、可视化、报告分别定义 ComponentSkill、VisualizationSkill、ReportSkill。

3. **改造 Executor**
   - WeatherExecutor._load_tools 改为 eturn skill_registry.load("meteorology")，其他 Executor 类似。

4. **完善依赖图**
   - 在 ackend/app/agent/core/tool_dependencies.py 中为 get_guangdong_regular_stations、ecord_note 等补充 input_bindings 和 output_fields，消除 input_bindings_not_found 警告。

### 3.4 RunLogger：统一运行日志

1. **新建 ackend/app/utils/run_logger.py**
   - 参考 mini_agent/logger.py:11-175：
     ``python
     class RunLogger:
         def start_new_run(self): ...
         def log_request(self, messages, tools): ...
         def log_response(self, content, thinking, tool_calls, finish_reason): ...
         def log_tool_result(self, tool_name, arguments, result_success, result): ...
         def end_run(self, status): ...
     ``
   - 日志文件放在 logs/agent_run_YYYYmmdd_HHMMSS.log。

2. **接入**
   - AgentShell.run() 开头/结尾调用 start_new_run() / end_run(status)。
   - ReActAgent.analyze 在 SSE “start” 事件返回 log 路径。
   - ExpertExecutor.execute 每次工具调用后 log_tool_result。

---

## 四、测试与上线

1. **单元测试**：	ests/tools/test_session_note.py、	ests/agent/test_skill_registry.py、	ests/agent/test_agent_shell.py。
2. **集成测试**：更新 ackend/tests/test_trajectory_*.py 确认技能注入有效；新增 ackend/tests/test_run_logger.py 检查日志格式。
3. **上线节奏**：
   - Sprint1：交付 AgentShell + RunLogger + Session Note。
   - Sprint2：SkillRegistry + 依赖图补齐。
   - Sprint3：报告专家依赖 ecall_notes，前端展示 run log 路径。

---

## 五、预期收益

- 统一入口：所有多专家执行在进入 Router 前都有统一上下文和 token 控制。
- 稳定记忆：Session Note + 自动摘要降低 token 压力，保证关键信息可跨会话复用。
- 技能化管理：新增/停用工具集中在技能层，依赖图完善后自动参数绑定更稳定。
- 可观测性提升：RunLogger 给每次任务生成独立日志文件，问题回溯效率大幅提升。
