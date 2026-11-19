// Agent 交互（structured question）解析的纯逻辑，从 reactStore 抽出以便
// node --test 直测；浮窗与全页工作区共用同一套续跑参数。

// structured question 回答后的续跑参数：agentMode 依次取解析结果、交互、
// 交互所在会话状态记录的模式；externalTarget（浮窗传入 targetState）时必须
// 原地续跑 assistant 会话（preserveCurrentMode），不抢全局当前模式。
export function buildQuestionResumeOptions({ resolution, interaction, interactionState, currentMode, externalTarget = false }) {
  return {
    agentMode: resolution?.mode || interaction?.mode || interactionState?.mode || currentMode,
    synthetic: true,
    syntheticMeta: { source: 'structured_question_resume', interaction_id: interaction?.interaction_id },
    queuedAlreadyShown: true,
    preserveCurrentMode: Boolean(externalTarget)
  }
}
