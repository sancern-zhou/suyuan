 ReAct架构 + 多专家调度完整工作流程分析

  基于代码分析，这是一个基于真正ReAct架构的智能大气污染分析系统，具有多专家协同调度能力。

  1. 系统整体架构

  ┌─────────────────────────────────────────────────────────────┐
  │                    ReActAgent (主控制器)                      │
  │  - 接收用户查询                                             │
  │  - 判断任务类型（多专家 vs 单专家）                          │
  │  - 协调记忆管理                                             │
  └────────────────────┬────────────────────────────────────────┘
                       │
           ┌───────────┴───────────┐
           │                       │
      ┌────▼────┐           ┌──────▼──────┐
      │ 多专家系统 │           │ 传统ReAct   │
      │ Expert   │           │   Loop      │
      │ RouterV3 │           │              │
      └────┬─────┘           └──────┬──────┘
           │                        │
      ┌────▼────────────────────────▼────┐
      │     HybridMemoryManager         │
      │  - Working (20条)                │
      │  - Session (压缩+文件系统)        │
      │  - LongTerm (向量存储)            │
      └─────────────────────────────────┘

  2. 多专家系统工作流程

  2.1 核心组件

  | 组件                    | 职责                 | 关键文件                       |
  |-----------------------|--------------------|----------------------------|
  | ExpertRouterV3        | 专家路由器：调度、并行执行      | expert_router_v3.py        |
  | StructuredQueryParser | 查询解析：NLP→结构化参数     | structured_query_parser.py |
  | ExpertPlanGenerator   | 计划生成：生成工具调用链       | expert_plan_generator.py   |
  | WeatherExecutor       | 气象专家：天气、轨迹、上风向     | weather_executor.py        |
  | ComponentExecutor     | 组分专家：污染源解析、PMF/OBM | component_executor.py      |
  | VizExecutor           | 可视化专家：图表生成         | expert_executor.py (基类)    |
  | ReportExecutor        | 报告专家：综合分析          | 同上                         |

  2.2 完整执行流程

  用户查询 → ReActAgent.analyze()
      │
      ├─[判断多专家任务]
      │  ├─关键词匹配："综合分析"、"完整分析"、"溯源分析"
      │  ├─多维度检查：气象+组分+可视化
      │  └─是 → 进入ExpertRouterV3
      │
      └─ExpertRouterV3.execute_pipeline()
          │
          ├─1. StructuredQueryParser.parse()
          │   ├─LLM提取：地点、时间、污染物、分析类型
          │   ├─城市坐标映射：肇庆市→(23.0469, 112.4651)
          │   ├─时间标准化："2025-11-7到2025-11-9" → ISO格式
          │   └─返回StructuredQuery对象
          │
          ├─2. ExpertPlanGenerator.determine_required_experts()
          │   ├─溯源任务/有经纬度 → 添加Weather专家
          │   ├─有污染物/分析任务 → 添加Component专家
          │   ├─分析/溯源任务 → 添加Viz专家
          │   ├─≥2个核心专家 → 添加Report专家
          │   └─返回专家列表：['weather', 'component', 'viz', 'report']
          │
          ├─3. ExpertPlanGenerator.generate()
          │   ├─构建上下文：{location, lat, lon, time, pollutants}
          │   ├─选择计划模板：default_plan vs tracing_plan
          │   ├─填充参数：{lat}、{start_time} → 实际值
          │   ├─处理依赖：工具A完成后执行工具B
          │   └─返回ExpertTask字典
          │
          ├─4. 分组并行执行
          │   ├─第1组（并行）：Weather + Component
          │   │   ├─WeatherExecutor.execute()
          │   │   │   ├─工具链：get_weather_data → trajectory_analysis
          │   │   │   ├─依赖处理：get_weather_data结果 → trajectory参数
          │   │   │   ├─错误重试：LLM修正参数，最多1次
          │   │   │   ├─专业总结：LLM生成气象分析
          │   │   │   └─返回：ExpertResult{status, data_ids, analysis}
          │   │   │
          │   │   └─ComponentExecutor.execute()
          │   │       ├─工具链：get_air_quality → get_component_data → calculate_obm_ofp
          │   │       ├─参数修正：自动纠正缺失参数
          │   │       ├─结果提取：data_id、统计摘要
          │   │       └─返回：ExpertResult
          │   │
          │   ├─第2组：Viz专家（等待前序结果）
          │   │   ├─update_plan_with_upstream() 替换占位符
          │   │   ├─$1 → 前序工具的data_id
          │   │   ├─工具链：smart_chart_generator
          │   │   └─返回：ExpertResult (包含visuals图表)
          │   │
          │   └─第3组：Report专家（等待所有结果）
          │       ├─收集所有专家的data_ids
          │       ├─综合分析：各专家结论整合
          │       └─返回：ExpertResult (综合报告)
          │
          ├─5. 结果聚合
          │   ├─_finalize_result()
          │   ├─统计：success/partial/failed专家数
          │   ├─生成最终答案：Report专家总结 或 各专家汇总
          │   ├─提取结论：key_findings → conclusions
          │   ├─置信度计算：各专家置信度加权平均
          │   └─返回：PipelineResult{status, final_answer, conclusions, data_ids}
          │
          └─ReActAgent返回：
              ├─expert_result事件：完整pipeline信息
              ├─complete事件：最终答案+置信度
              └─data_ids：供前端引用数据

  3. 单个专家执行流程

  以WeatherExecutor为例：

  ExpertExecutor.execute(task)
      │
      ├─1. 工具依赖图初始化
      │   ├─加载tool_dependencies.py中的依赖配置
      │   ├─解析input_bindings：支持6种绑定表达式类型
      │   └─验证参数绑定配置有效性
      │
      ├─2. 参数绑定器(ParameterBinder)处理
      │   ├─_parse_binding_expression() 解析绑定表达式
      │   │   ├─indexed_tool: "get_weather_data[0]"
      │   │   ├─field_access: "get_weather_data[0].data_id"
      │   │   ├─context_field: "{lat}", "{location}"
      │   │   ├─context_nested: "get_weather_data[0].context.lat"
      │   │   ├─wildcard: "weather:*", "component:*"
      │   │   └─special_value: "{auto_generate}", "{first_available}"
      │   │
      │   ├─bind_parameters() 智能参数绑定
      │   │   ├─非字符串类型直接传递：hours=72 (数字)
      │   │   ├─上下文参数解析：{lat} → 23.0469
      │   │   ├─上游结果提取：tool_result.get_field("data_id")
      │   │   └─特殊值处理：{auto_generate} → 自动生成查询
      │   │
      │   └─返回绑定后的参数字典
      │
      ├─3. 工具链执行(_execute_tool_chain)
      │   ├─找出可执行工具（依赖已满足）
      │   ├─并行执行就绪工具
      │   └─循环直到所有工具执行完毕
      │
      ├─4. 单工具执行(_execute_single_tool)
      │   ├─参数解析：{lat} → 23.0469, $1 → 上序data_id
      │   ├─第一次尝试：tool.execute(**params)
      │   ├─失败且可重试：
      │   │   ├─_correct_params() 调用轻量LLM
      │   │   ├─根据错误信息修正参数
      │   │   └─重试执行
      │   └─返回：{tool, status, result/error, data_id}
      │
      ├─5. Context-Aware V2数据管理
      │   ├─context.save_data() 自动标准化
      │   │   ├─强制应用UDF v2.0格式
      │   │   ├─添加schema_version="v2.0"
      │   │   ├─字段映射：260个字段标准化
      │   │   └─返回字符串data_id（简化设计）
      │   │
      │   ├─错误处理机制
      │   │   ├─parameter_binding_error → 记录错误，使用默认值
      │   │   ├─field_access_failed → 记录警告，返回None
      │   │   └─unmatched_binding_expression → 保留原值
      │   └─返回：{tool, status, result/error, data_id}
      │
      ├─6. _generate_summary()
      │   ├─LLM调用：专业领域提示词
      │   ├─输入：工具统计+摘要数据
      │   ├─输出：ExpertAnalysis{summary, key_findings, confidence}
      │   └─返回：JSON格式专业总结
      │
      ├─7. 结果封装
      │   ├─_extract_data_ids() 提取所有data_id
      │   ├─_build_execution_summary() 执行统计
      │   ├─_determine_status() 判断状态
      │   └─返回：ExpertResult对象
      │
      └─ExpertResult{
          status: "success/partial/failed",
          data_ids: ["data_id_1", "data_id_2"],
          analysis: ExpertAnalysis,
          execution_summary: ExecutionSummary,
          tool_results: [...]
      }

  4. 传统ReAct循环（备用模式）

  ReActLoop.run(query)
      │
      ├─1. 增强查询（RAG）
      │   ├─enhance_with_longterm() 检索相似任务
      │   ├─长期记忆：Qdrant向量库
      │   └─返回：增强后的上下文
      │
      ├─2. ReAct循环（最多10次迭代）
      │   ├─Thought阶段：
      │   │   ├─get_enhanced_context_for_llm() 获取实际数据
      │   │   ├─planner.generate_thought() LLM思考
      │   │   └─返回：Thought{thought, reasoning}
      │   │
      │   ├─Action阶段：
      │   │   ├─planner.decide_action() LLM决策
      │   │   ├─工具选择：根据可用工具动态决定
      │   │   └─返回：Action{type: "TOOL_CALL"/"FINISH", tool, args}
      │   │
      │   └─Observation阶段：
      │       ├─tool_executor.execute_tool() 调用工具
      │       ├─reflexion_handler.handle_error() 错误处理
      │       ├─处理visuals：图表信息加入工作记忆
      │       └─返回：Observation{success, data, data_id}
      │
      ├─3. 记忆管理
      │   ├─add_iteration() → WorkingMemory
      │   ├─压缩：每10次 → SessionMemory
      │   ├─保存：会话结束 → LongTermMemory
      │   └─清理：超大数据外部化到文件系统
      │
      └─4. 返回结果
          ├─complete：最终答案+迭代数
          ├─incomplete：部分答案+原因
          └─fatal_error：错误信息

  5. 关键设计亮点

  5.1 真正的Agent架构

  - ❌ 无固定工作流：不使用预设流程
  - ❌ 无关键词匹配：LLM自主理解意图
  - ✅ 动态工具选择：每次调用由LLM决定
  - ✅ 真正ReAct循环：Thought→Action→Observation循环

  5.2 智能参数绑定系统(ParameterBinder)

  5.2.1 支持6种绑定表达式类型

  ├─indexed_tool: "get_weather_data[0]"
  ├─field_access: "get_weather_data[0].data_id"
  ├─context_field: "{lat}", "{location}"
  ├─context_nested: "get_weather_data[0].context.lat"
  ├─wildcard: "weather:*", "component:*"
  └─special_value: "{auto_generate}", "{first_available}"

  5.2.2 智能类型处理

  # 修复前：无法处理非字符串类型
  if not isinstance(binding_expr, str):
      raise TypeError("expected string or bytes-like object")  # ❌ 错误

  # 修复后：非字符串类型直接传递
  if not isinstance(binding_expr, str):
      bound_params[param_name] = binding_expr  # ✅ 正确：hours=72
      continue

  5.2.3 字段路径修复

  # 修复前：依赖上游工具结果（可能失败）
  "input_bindings": {
      "lat": "get_weather_data[0].result.lat",  # ❌ 错误：使用result.xxx
      "lon": "get_weather_data[0].result.lon"
  }

  # 修复后：使用上下文参数（稳定可靠）
  "input_bindings": {
      "lat": "{lat}",  # ✅ 正确：从上下文获取
      "lon": "{lon}"
  }

  5.3 工具依赖图优化(TOOL_DEPENDENCY_GRAPHS)

  5.3.1 工具分类

  | 分类   | 工具示例                          | 参数绑定特点                    |
  |-------|-----------------------------------|------------------------------|
  | 查询型 | get_air_quality, get_component_data | input_bindings: {} (不使用绑定) |
  | 分析型 | calculate_pmf, calculate_obm_ofp     | input_bindings: 使用data_id     |
  | 可视化 | smart_chart_generator, generate_chart | input_bindings: 混合绑定         |

  5.3.2 查询分发逻辑修复

  # 修复前：所有工具生成相同占位符
  question = "{auto_generate}"  # ❌ 错误：未解析占位符

  # 修复后：不同工具生成不同查询
  if tool_name == "get_air_quality":
      question = f"查询{location}期间的PM2.5、PM10、O3等常规污染物"  # ✅
  elif tool_name == "get_component_data":
      question = f"查询{location}的VOCs挥发性有机化合物组分数据"  # ✅

  5.4 智能参数修正机制

  # 第一次调用失败
  tool.execute(**params) → ERROR

  # LLM自动修正
  LLM: {
      "错误": "missing required argument 'context'",
      "原始参数": {...},
      "工具schema": {...}
  } → LLM → {
      "corrected_params": {...}
  }

  # 重试执行
  tool.execute(**corrected_params) → SUCCESS

  5.5 Context-Aware V2数据管理

  5.5.1 强制UDF v2.0标准化

  # 工具内部
  context = get_context_from_agent()
  data_id = context.save_data(data=[...], schema="vocs_unified")
  return {
      "data_id": data_id,
      "status": "success",
      "metadata": {
          "schema_version": "v2.0",           # ✅ 强制版本标记
          "field_mapping_applied": true,      # ✅ 强制标准化标记
          "field_mapping_info": {...},        # ✅ 强制映射统计
          "generator": "tool_name",
          "scenario": "scenario"
      }
  }

  5.5.2 字符串ID架构（简化设计）

  # ✅ 正确用法：直接返回字符串ID
  data_id = context.save_data(data=[...], schema="vocs_unified")
  result["data_id"] = data_id  # 字符串ID，可直接赋值

  # ❌ 错误理解：不返回Handle对象
  # handle = context.save_data(...)  # 错误！返回的是字符串
  # data_id = handle.full_id         # 不需要此步骤

  5.5.3 记忆管理（引用而非存储）

  observation = {
      "data_id": "data_id_1",
      "data_ref": "data_id_1",  # 轻量级引用
      "instructions": "如需完整数据，调用 load_data_from_memory(data_ref='data_id_1')"
  }

  5.6 专业领域分工

  | 专家        | 工具集                                                       | 分析重点          |
  |-----------|-----------------------------------------------------------|---------------|
  | Weather   | get_weather_data, trajectory_analysis, upwind_enterprises | 气象条件、传输路径、上风向 |
  | Component | get_air_quality, get_component_data, calculate_pmf, calculate_obm_ofp | 污染物浓度、源解析、OFP |
  | Viz       | smart_chart_generator, generate_chart                     | 数据可视化、图表生成    |
  | Report    | (无工具)                                                     | 综合分析、报告撰写     |

  5.7 依赖图调度

  5.7.1 工具执行顺序自动处理

  tool_plan = [
      {"tool": "get_weather_data", "depends_on": []},
      {"tool": "trajectory_analysis", "depends_on": [0]}  # 依赖工具0的结果
  ]

  # 执行器自动调度
  execute_group():
      for tool in ready_tools:  # 依赖已满足
          execute_tool(tool)

  5.7.2 并行与顺序执行策略

  ├─第1组（并行）：Weather + Component
  │   ├─工具无相互依赖
  │   └─可同时执行提高效率
  │
  ├─第2组（顺序）：Viz专家
  │   ├─依赖前序结果：$1 → 前序data_id
  │   └─等待第1组完成后执行
  │
  └─第3组（顺序）：Report专家
      ├─依赖所有结果：{all_results}
      └─等待所有组完成后执行

  6. 统一规范保持性分析

  基于Expert系统运行时问题修复，确认以下统一规范完整保持：

  6.1 UDF v2.0统一数据格式 ✅

  ├─修复后的工具输出完全遵循UDF v2.0标准：
  │   ├─status: "success|failed|partial|empty"
  │   ├─success: true|false
  │   ├─data: [标准化后的数据列表]
  │   ├─metadata: {
  │   │   ├─schema_version: "v2.0"        # ✅ 必填：格式版本
  │   │   ├─field_mapping_applied: true,   # ✅ 必填：标准化标记
  │   │   ├─field_mapping_info: {...},     # ✅ 必填：映射统计
  │   │   ├─source_data_ids: ["..."],      # 源数据ID列表
  │   │   ├─generator: "tool_name",        # 生成工具名称
  │   │   ├─scenario: "scenario",          # 场景标识
  │   │   ├─record_count: 100,             # 记录数量
  │   │   └─generator_version: "2.0.0"     # 工具版本
  │   └─summary: "摘要信息"
  │
  ├─多图表场景使用visuals字段：
  │   ├─data: null                          # v2.0不使用data承载图表
  │   ├─visuals: [                          # ✅ 统一visuals字段
  │   │   └─{
  │   │       ├─id: "visual_001",
  │   │       ├─type: "chart|map|table",
  │   │       ├─schema: "chart_config",
  │   │       ├─payload: {图表v3.1格式},
  │   │       └─meta: {
  │   │           ├─schema_version: "v2.0",
  │   │           ├─source_data_ids: ["..."],
  │   │           ├─generator: "tool_name",
  │   │           └─scenario: "scenario"
  │   └─metadata: {schema_version: "v2.0"}
  │
  └─Context-Aware V2强制标准化钩子：
      ├─DataContextManager.save_data() 自动应用标准化
      ├─所有输出自动添加schema_version="v2.0"
      ├─字段映射系统自动应用260个字段映射
      └─field_mapping_applied=true自动标记

  6.2 Chart v3.1图表配置规范 ✅

  ├─所有图表数据遵循v3.1标准：
  │   ├─id: "图表ID"
  │   ├─type: "pie|bar|line|timeseries|wind_rose|profile|map|..."  # 15种类型
  │   ├─title: "标题"
  │   ├─data: {图表数据}
  │   └─meta: {
  │       ├─schema_version: "3.1",              # ✅ 图表格式版本
  │       ├─generator: "生成器标识",              # 与UDF v2.0对齐
  │       ├─original_data_ids: ["源数据ID"],      # 源数据ID
  │       ├─scenario: "场景标识",                 # 与UDF v2.0对齐
  │       ├─layout_hint: "wide|tall|map-full|side|main",  # 布局提示
  │       ├─interaction_group: "chart_interaction",        # 交互组
  │       └─data_flow: ["data_source", "chart_config"]     # 数据流
  │   }
  │
  ├─支持的图表类型（15种）：
  │   ├─基础: pie, bar, line, timeseries
  │   ├─气象: wind_rose（风向玫瑰图）, profile（边界层廓线图）
  │   ├─3D: scatter3d, surface3d, line3d, bar3d, volume3d
  │   └─高级: heatmap, radar, map（高德地图）
  │
  └─数据类型规范：
      ├─饼图: [{"name": "...", "value": ...}]
      ├─柱/线图: {"x": [], "y": []} 或 {"x": [], "series": [...]}
      ├─时序图: {"x": [], "series": [{"name": "...", "data": [...]}]}
      ├─风向玫瑰: {"sectors": [{"direction": "N", "avg_speed": 3.5}]}
      ├─边界层廓线: {"altitudes": [...], "elements": [{"name": "温度", "data": [...]}]}
      └─地图: {"map_center": {lng, lat}, "zoom": 12, "layers": [...]}

  6.3 字段映射系统保持 ✅

  ├─260个字段映射完整保留：
  │   ├─气象字段: 110个（支持中文字段：气温→temperature_2m）
  │   ├─类别覆盖: 时间、站点、坐标、污染物、AQI、VOCs、颗粒物、气象、元数据
  │   └─特性: 支持大小写不敏感、驼峰命名、中文映射
  │
  ├─自动字段映射：
  │   ├─通过DataContextManager.save_data()强制应用
  │   ├─field_mapping_info统计映射结果
  │   └─field_mapping_applied=true标记已应用
  │
  └─向后兼容：
      ├─支持旧版字段名
      ├─自动转换为标准字段名
      └─保留原始字段信息在metadata中
