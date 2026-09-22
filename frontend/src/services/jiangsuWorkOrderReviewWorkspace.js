// 故障工单审核工作区的 Agent 命令契约。
// Agent 通过工具结果里的 data.ui_command 驱动右侧「工单审核」tab；
// 业务变更（反馈/归档/退回）仍走经过鉴权的显式 API，由用户确认触发。

export const WORK_ORDER_REVIEW_COMMANDS = Object.freeze({
  OPEN: 'open_work_order_review',
})

export function extractWorkOrderReviewCommand(messages = []) {
  for (const message of [...messages].reverse()) {
    if (message?.type !== 'tool_result') continue
    const result = message.data?.result || {}
    const command = result.data?.ui_command || result.ui_command
    if (command?.type === WORK_ORDER_REVIEW_COMMANDS.OPEN && command.working_order_code) {
      return command
    }
  }
  return null
}
