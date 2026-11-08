# 助手委派轮询风暴问题说明（2026-11-08）

## 现象

2026-11-08 10:37–11:00，助手模式会话 `assistant_session_1794105295576_oehrfu044`（用户请求"生成昨日的环境质量简报"）运行 21.5 分钟后以 **status=timeout** 收场，落库 318 条消息。用户最终只拿到中途的口头数据摘要，**"终值版"Word 简报未交付**。

## 问题清单（按严重度）

### 1. 委派轮询风暴（最严重）

- 主 Agent 对 `manage_assistant_runs` 空转调用 **243 次**，触发 3 次 loop guard（"已重复调用 5 次，系统已阻止"）。
- 根因：`run_agent_workflow` / `call_sub_agent` 受理后仅返回"委派已受理，请用 manage_assistant_runs 查询"，而委派完成后的**结果回灌（`_absorb_background_delegations` 等待边界）未覆盖本次这些委派**，主 Agent 只能把它当唯一进度通道反复轮询。
- thinking 记录显示模型自己也意识到"轮询浪费 turns"，但未改用 `wait_task` 阻塞等待——工具描述未做引导。

### 2. office 子 Agent 偏航，docx 一直未产出

- office 委派（`delegation_a415254c...`）没写 Word 文档而是去做"数据核对"，长时间 running。
- 简报 docx 被反复覆写：read_file 结果在 5段/7段1表/5段/1段/4段 之间来回变化（疑似反复覆盖写坏），主 Agent 用 7 次 read_file 逐段核对仍未定稿。

### 3. workflow 误标 partial（假阴性）

- 三个节点全部 succeeded，但资源契约存在 json vs csv 格式不匹配，整个 workflow 被标为 `partial`，误导主 Agent 继续排查"缺了什么"。模型 thinking 自述："The workflow is partial only due to resource contract format mismatches (json vs csv), not actual missing content."

### 4. 子 Agent 会话内存为空

- 大量 `get_messages_for_llm_empty`（`assistant__to__office__*`、`assistant__to__query_monitoring_*` 的 history_length=0）+ 一次 `session_memory_cleanup_failed`。委派出的子会话上下文没有积累，可能是子 Agent 偏航的诱因之一。

### 5. 上下文重复注入放大 token 消耗

- `fresh_tool_result_projection` 每轮注入 13–18K 字符的大工具结果；243 次轮询叠加后 history_tokens 升至 28K+，最终 timeout。

## 正常用法 vs 本次实际

`manage_assistant_runs` 设计动作为 list/get/result/cancel/steer。正常链路：委派受理 → get 确认一次 → 若仍 running 则等回灌（`wait_for_session_runs`）或干别的 → 完成后 result 读取。本次因回灌失效，轮询成了唯一选择。

## 修复方向（待排期）

1. 委派受理后引导/强制走阻塞等待（`wait_task`，或 `manage_assistant_runs` 支持 block=true 长轮询），消除轮询风暴。
2. 排查 `_absorb_background_delegations` 为何未等待本会话委派（疑似 detach/后台模式或等待边界判断遗漏）。
3. workflow 资源契约 json/csv mismatch 降为 warning，不整体降级 partial。
4. office 子 Agent 产出校验：声明生成 docx 而实际未产出时不得报 success；查明反复覆写原因。
5. 子 Agent 会话内存 history_length=0 的原因排查。

## 同日已修复的关联问题

- docx 发布到文件面板被拒（`resource_declaration_invalid`）：`ResourceRenderer` 枚举缺 `docx` 值，已补（commit `a06743ac`）。该问题导致 11-07 会话第一次 `publish_session_file` 失败、靠 PDF 派生件重试成功。
