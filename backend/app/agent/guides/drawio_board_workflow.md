# Draw.io Board Workflow

本文件是图表模式 draw.io 画板任务的强约束流程。只适用于 `mode=chart`。

## 入口判断

当用户要求创建、修改、整理、扩展、重绘、连接、布局、解释或继续编辑可交互画板时，必须使用 `create_drawio_board`。

不得在图表模式使用 `create_diagram_artifact` 处理画板任务。

## 权威状态

1. 前端传入的 `board_context.current_xml` 是当前画布的权威状态。
2. 除非用户明确要求重建整张图，否则不得丢弃现有 XML 后重新生成。
3. 修改现有画板时，应优先做局部编辑，保留未被用户要求修改的节点、连线、样式和布局。

## 多轮工作流

1. 读取本文件、`drawio_xml_rules.md` 和 `drawio_edit_policy.md`。
2. 判断任务是新建画板还是编辑现有画板。
3. 按“专项设计文档路由”读取与任务匹配的设计文档；如果任务只做局部文字、颜色、位置调整，可以不读取专项设计文档。
4. 新建画板时，调用 `create_drawio_board(operation="create")`，传入完整可渲染 XML。
5. 编辑画板时，基于 `board_context.current_xml` 理解现有画板，并调用 `create_drawio_board(operation="edit")` 提交结构化 `operations`。
6. 如果用户选择了画布元素，优先用 `board_context.selected_cells` 解释“这个”“这里”“选中的模块”等指代。
7. 工具返回失败时，先修正 XML 或 operations，再重试；不要直接向用户输出无法渲染的 XML。

## 专项设计文档路由

根据用户任务选择性读取以下文档，避免把所有图型规则一次性塞入上下文：

1. 系统架构、技术架构、部署架构、微服务关系、云架构：读取 `app/agent/guides/drawio_patterns/architecture.md`。
2. 业务流程、审批流程、处置流程、算法步骤、运维流程：读取 `app/agent/guides/drawio_patterns/process_flow.md`。
3. 数据采集、清洗、分析、报表、模型推理、数据血缘：读取 `app/agent/guides/drawio_patterns/data_flow.md`。
4. 判断逻辑、规则引擎、告警分级、分诊流程：读取 `app/agent/guides/drawio_patterns/decision_tree.md`。
5. 平台能力、产品架构、能力地图、治理体系、分层系统：读取 `app/agent/guides/drawio_patterns/layered_system.md`。
6. 路线图、时间线、里程碑、计划排期：读取 `app/agent/guides/drawio_patterns/timeline.md`。
7. 方案对比、指标对比、城市对比、工具/策略对比：读取 `app/agent/guides/drawio_patterns/comparison_matrix.md`。

如果任务同时命中多个类型，优先选择用户主诉最强的 1 到 2 份专项文档；不要无差别读取全部文档。

## 回复要求

完成工具调用后，用简短自然语言说明改动结果。不要把完整 XML 粘贴给用户，除非用户明确要求查看 XML。
