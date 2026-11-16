// 智能体平台卡片可见性策略。
// 助手模式的统一入口是浮球/浮窗（assistant_floating 特性）与 App ?assistant=1 深链，
// 启用浮窗的项目平台页不再重复展示助手卡片；未启用浮窗的项目保持原样
// （如江西，assistant 被项目定义为正式工作智能体，平台卡片是它的唯一入口）。
export const filterPlatformAgentCards = (agents, { assistantFloating } = {}) => (
  assistantFloating ? agents.filter(agent => agent.id !== 'assistant') : agents
)
