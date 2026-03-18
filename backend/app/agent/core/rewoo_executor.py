"""
ReWOO Executor Module

实现 ReWOO (Reasoning WithOut Observation) 执行逻辑。

核心特性：
1. 一次性规划：生成完整执行计划
2. 依赖分析：识别步骤间的依赖关系
3. 并行执行：独立步骤并发执行
4. 减少 LLM 调用：80%+ 成本节省
"""
from typing import Dict, Any, AsyncGenerator, List, Optional
from datetime import datetime
import asyncio
import re
import structlog

logger = structlog.get_logger()


class ExecutionPlan:
    """执行计划数据结构"""

    def __init__(
        self,
        steps: List[str],
        dependencies: Dict[str, List[str]],
        parallel_groups: List[List[str]]
    ):
        self.steps = steps
        self.dependencies = dependencies
        self.parallel_groups = parallel_groups
        self.results: Dict[str, Any] = {}  # 存储每个步骤的执行结果


class ReWOOExecutor:
    """
    ReWOO 执行器

    实现基于预先规划的执行模式。
    """

    def __init__(self, memory_manager, llm_planner, tool_executor):
        """
        初始化 ReWOO 执行器

        Args:
            memory_manager: 混合记忆管理器
            llm_planner: LLM 规划器
            tool_executor: 工具执行器
        """
        self.memory = memory_manager
        self.planner = llm_planner
        self.executor = tool_executor

    async def execute_plan(
        self,
        user_query: str,
        max_iterations: int = 10
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 ReWOO 规划模式

        Args:
            user_query: 用户查询
            max_iterations: 最大迭代次数（ReWOO 模式下通常不需要）

        Yields:
            流式事件
        """
        logger.info("rewoo_execution_start", query=user_query[:100])

        try:
            # Step 1: 生成执行计划
            yield {
                "type": "plan_generating",
                "data": {
                    "message": "正在生成执行计划...",
                    "timestamp": datetime.now().isoformat()
                }
            }

            plan = await self._generate_plan(user_query)

            yield {
                "type": "plan_generated",
                "data": {
                    "steps": plan.steps,
                    "parallel_groups": plan.parallel_groups,
                    "total_steps": len(plan.steps),
                    "timestamp": datetime.now().isoformat()
                }
            }

            logger.info(
                "rewoo_plan_created",
                total_steps=len(plan.steps),
                parallel_groups_count=len(plan.parallel_groups)
            )

            # Step 2: 按并行组执行
            total_executed = 0

            for group_index, group in enumerate(plan.parallel_groups, 1):
                yield {
                    "type": "group_executing",
                    "data": {
                        "group_index": group_index,
                        "group_size": len(group),
                        "steps": group,
                        "timestamp": datetime.now().isoformat()
                    }
                }

                # 并行执行当前组的所有步骤
                group_results = await self._execute_group(plan, group)

                # 更新计划结果
                plan.results.update(group_results)

                total_executed += len(group)

                # 发送组完成事件
                yield {
                    "type": "group_completed",
                    "data": {
                        "group_index": group_index,
                        "completed_steps": total_executed,
                        "total_steps": len(plan.steps),
                        "progress": total_executed / len(plan.steps),
                        "timestamp": datetime.now().isoformat()
                    }
                }

            # Step 3: 生成最终答案
            yield {
                "type": "synthesizing",
                "data": {
                    "message": "正在综合分析结果...",
                    "timestamp": datetime.now().isoformat()
                }
            }

            final_answer = await self._synthesize_answer(
                user_query,
                plan
            )

            # Note: 长期记忆保存已移除

            yield {
                "type": "complete",
                "data": {
                    "answer": final_answer,
                    "total_steps": len(plan.steps),
                    "execution_mode": "rewoo",
                    "session_id": self.memory.session_id,
                    "timestamp": datetime.now().isoformat()
                }
            }

            logger.info(
                "rewoo_execution_complete",
                total_steps=len(plan.steps),
                session_id=self.memory.session_id
            )

        except Exception as e:
            logger.error(
                "rewoo_execution_failed",
                error=str(e),
                exc_info=True
            )

            yield {
                "type": "error",
                "data": {
                    "error": f"ReWOO 执行失败: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            }

    async def _generate_plan(self, user_query: str) -> ExecutionPlan:
        """
        生成执行计划

        Args:
            user_query: 用户查询

        Returns:
            ExecutionPlan 对象
        """
        # 获取上下文
        context = self.memory.get_context_for_llm()

        # 构建规划提示词
        planning_prompt = self._build_planning_prompt(user_query, context)

        # 调用 LLM 生成计划
        from app.services.llm_service import llm_service

        response = await llm_service.chat(
            messages=[{"role": "user", "content": planning_prompt}],
            temperature=0.3
        )

        # 解析计划
        plan = self._parse_plan(response)

        return plan

    def _build_planning_prompt(
        self,
        user_query: str,
        context: str
    ) -> str:
        """构建规划提示词"""

        # 获取可用工具列表
        tools_desc = self._format_tools_description()

        prompt = f"""
你是大气污染溯源分析系统的规划专家。请为以下任务生成完整的执行计划。

## 任务
{user_query}

## 可用工具
{tools_desc}

## 规划要求

1. **完整性**: 一次性生成所有必要步骤，不要遗漏
2. **并行性**: 独立的步骤应该能够并行执行
3. **依赖性**: 明确标注步骤间的依赖关系
4. **格式**: 严格按照以下格式输出

## 输出格式

每个步骤格式：
```
#E1 = tool_name(arg1='value1', arg2='value2')
#E2 = tool_name2(arg1='value1')
#E3 = tool_name3(data=#E1, other=#E2)  # 可以引用之前的结果
```

注意：
- 使用 #E1, #E2, #E3... 标识每个步骤
- 可以用 #E1, #E2 引用之前步骤的结果
- 独立的步骤应该能同时执行（如 #E1 和 #E2）
- 工具参数要具体明确

## 典型分析流程参考

对于大气污染溯源任务，通常需要：
1. 获取气象数据（温度、风速、风向等）
2. 获取空气质量数据（目标污染物浓度）
3. 分析上风向企业（基于风场）
4. 获取污染物组分数据（如VOCs或PM组分）
5. 生成可视化图表
6. 综合生成分析报告

## 执行计划

请生成计划（只输出计划步骤，不要其他解释）：
"""

        return prompt

    def _format_tools_description(self) -> str:
        """格式化工具列表"""
        tools = self.executor.list_available_tools()

        descriptions = []
        for tool_name in tools:
            tool_info = self.executor.get_tool_info(tool_name)
            if tool_info:
                desc = tool_info.get("doc", "无描述")
                descriptions.append(f"- **{tool_name}**: {desc}")

        return '\n'.join(descriptions)

    def _parse_plan(self, response: str) -> ExecutionPlan:
        """
        解析 LLM 生成的计划

        Args:
            response: LLM 响应文本

        Returns:
            ExecutionPlan 对象
        """
        # 提取所有步骤
        lines = response.strip().split('\n')
        steps = []

        for line in lines:
            line = line.strip()
            # 匹配 #E1 = tool(...) 格式
            if re.match(r'#E\d+\s*=\s*\w+\([^)]*\)', line):
                steps.append(line)

        if not steps:
            logger.warning("no_steps_parsed", response=response)
            raise ValueError("无法解析执行计划，请检查LLM输出格式")

        # 分析依赖关系
        dependencies = self._extract_dependencies(steps)

        # 划分并行执行组
        parallel_groups = self._create_parallel_groups(steps, dependencies)

        return ExecutionPlan(
            steps=steps,
            dependencies=dependencies,
            parallel_groups=parallel_groups
        )

    def _extract_dependencies(self, steps: List[str]) -> Dict[str, List[str]]:
        """
        提取依赖关系

        Example:
        #E3 = analyze(data=#E1, weather=#E2)
        -> {"E3": ["E1", "E2"]}
        """
        dependencies = {}

        for step in steps:
            # 提取步骤ID (E1, E2, ...)
            match = re.match(r'#(E\d+)', step)
            if not match:
                continue

            step_id = match.group(1)

            # 查找所有引用 (#E1, #E2)
            refs = re.findall(r'#(E\d+)', step)

            # 移除自己的ID，只保留依赖的ID
            deps = [ref for ref in refs if ref != step_id]

            if deps:
                dependencies[step_id] = deps

        return dependencies

    def _create_parallel_groups(
        self,
        steps: List[str],
        dependencies: Dict[str, List[str]]
    ) -> List[List[str]]:
        """
        创建并行执行组

        算法：拓扑排序 + 分层
        """
        # 提取所有步骤ID
        step_ids = []
        for step in steps:
            match = re.match(r'#(E\d+)', step)
            if match:
                step_ids.append(match.group(1))

        # 计算每个步骤的层级（最大依赖深度）
        levels = {}

        def get_level(step_id: str) -> int:
            if step_id in levels:
                return levels[step_id]

            deps = dependencies.get(step_id, [])
            if not deps:
                levels[step_id] = 0
                return 0

            max_dep_level = max(get_level(dep) for dep in deps)
            levels[step_id] = max_dep_level + 1
            return levels[step_id]

        # 计算所有步骤的层级
        for step_id in step_ids:
            get_level(step_id)

        # 按层级分组
        max_level = max(levels.values()) if levels else 0
        parallel_groups = []

        for level in range(max_level + 1):
            group = [sid for sid, lvl in levels.items() if lvl == level]
            if group:
                parallel_groups.append(group)

        logger.info(
            "parallel_groups_created",
            total_steps=len(step_ids),
            groups_count=len(parallel_groups),
            groups=parallel_groups
        )

        return parallel_groups

    async def _execute_group(
        self,
        plan: ExecutionPlan,
        group: List[str]
    ) -> Dict[str, Any]:
        """
        并行执行一组独立的步骤

        Args:
            plan: 执行计划
            group: 步骤ID列表

        Returns:
            步骤ID -> 执行结果的映射
        """
        # 解析每个步骤
        tasks = []
        step_mappings = {}

        for step_id in group:
            # 找到对应的步骤文本
            step_text = next(
                (s for s in plan.steps if s.startswith(f"#{step_id}")),
                None
            )

            if not step_text:
                logger.warning("step_not_found", step_id=step_id)
                continue

            # 解析工具调用
            tool_call = self._parse_step(step_text, plan.results)

            if tool_call:
                tasks.append(self._execute_tool_call(tool_call))
                step_mappings[step_id] = tool_call

        # 并行执行
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # 组装结果
        group_results = {}
        for i, step_id in enumerate(group):
            if i < len(results_list):
                group_results[step_id] = results_list[i]

        return group_results

    def _parse_step(
        self,
        step_text: str,
        previous_results: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        解析步骤为工具调用

        Args:
            step_text: 步骤文本 (e.g., "#E1 = get_weather_data(city='广州')")
            previous_results: 之前步骤的结果

        Returns:
            工具调用字典
        """
        # 提取工具名和参数
        match = re.match(r'#E\d+\s*=\s*(\w+)\(([^)]*)\)', step_text)
        if not match:
            logger.warning("step_parse_failed", step=step_text)
            return None

        tool_name = match.group(1)
        args_str = match.group(2)

        # 解析参数
        tool_args = {}
        if args_str.strip():
            # 简单解析（生产环境需要更robust的解析器）
            args_parts = [p.strip() for p in args_str.split(',')]

            for part in args_parts:
                if '=' in part:
                    key, value = part.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # 处理引用
                    if value.startswith('#E'):
                        ref_id = value[1:]  # 去掉 #
                        if ref_id in previous_results:
                            tool_args[key] = previous_results[ref_id]
                        else:
                            logger.warning(
                                "reference_not_found",
                                ref=value,
                                available=list(previous_results.keys())
                            )
                    # 处理字符串
                    elif value.startswith("'") or value.startswith('"'):
                        tool_args[key] = value.strip("'\"")
                    # 处理数字
                    else:
                        try:
                            tool_args[key] = float(value) if '.' in value else int(value)
                        except ValueError:
                            tool_args[key] = value

        return {
            "tool": tool_name,
            "args": tool_args
        }

    async def _execute_tool_call(
        self,
        tool_call: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行单个工具调用

        Args:
            tool_call: 工具调用信息

        Returns:
            工具执行结果
        """
        try:
            result = await self.executor.execute_tool(
                tool_name=tool_call["tool"],
                tool_args=tool_call["args"]
            )
            return result
        except Exception as e:
            logger.error(
                "tool_execution_failed",
                tool=tool_call["tool"],
                error=str(e)
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def _synthesize_answer(
        self,
        user_query: str,
        plan: ExecutionPlan
    ) -> str:
        """
        综合所有结果生成最终答案

        Args:
            user_query: 用户查询
            plan: 执行计划（包含所有结果）

        Returns:
            最终答案文本
        """
        # 格式化执行结果
        results_summary = self._format_results_summary(plan)

        synthesis_prompt = f"""
基于以下执行结果，为用户查询生成综合分析报告。

## 用户查询
{user_query}

## 执行结果
{results_summary}

## 任务
请综合所有数据，生成一份清晰、专业的分析报告。报告应包括：
1. 关键发现
2. 数据分析
3. 结论和建议

请直接输出报告内容，使用Markdown格式。
"""

        from app.services.llm_service import llm_service

        final_answer = await llm_service.chat(
            messages=[{"role": "user", "content": synthesis_prompt}],
            temperature=0.5
        )

        return final_answer

    def _format_results_summary(self, plan: ExecutionPlan) -> str:
        """格式化结果摘要"""
        lines = []

        for step_id, result in plan.results.items():
            # 找到步骤文本
            step_text = next(
                (s for s in plan.steps if s.startswith(f"#{step_id}")),
                f"#{step_id}"
            )

            if isinstance(result, dict):
                success = result.get("success", False)
                status = "✅ 成功" if success else "❌ 失败"

                lines.append(f"{step_text}")
                lines.append(f"  状态: {status}")

                if "data" in result:
                    data_str = str(result["data"])[:200]
                    lines.append(f"  结果: {data_str}...")
                elif "error" in result:
                    lines.append(f"  错误: {result['error']}")

        return "\n".join(lines)
