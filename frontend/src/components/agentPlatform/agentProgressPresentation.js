const GENERAL_TIPS = Object.freeze([
  '说明目标、可用资料和输出格式，Agent 会更快对齐需求',
  '复杂任务可以分步提出，先确认方向再继续完善',
  '结果不理想时，直接指出需要调整的段落、语气或篇幅',
  '提供一个满意的参考样例，通常比抽象描述更有效',
  '不同目标建议使用不同会话，避免上下文相互干扰',
  '模型挡位在输入框左侧切换：快速模式响应快，深度思考更严谨',
  '日常问数和查询用快速模式更流畅；报告、研判等复杂任务建议深度思考',
  '不确定怎么选就用自动：主对话深度思考，子任务自动加速'
])

const MODE_TIPS = Object.freeze({
  assistant: [
    '补充使用场景和目标读者，内容会更贴合实际需要',
    '可以先让我列出所需信息，再开始执行复杂任务'
  ],
  query: [
    '指定时间范围、区域、指标和统计口径，查询结果会更准确',
    '需要对比分析时，可以同时说明基准时段和排序方式'
  ],
  knowledge: [
    '指定知识库、文档或章节范围，可以减少无关检索',
    '需要核验结论时，可以要求同时给出原文依据'
  ],
  expert: [
    '说明决策场景和约束条件，有助于专家给出更可执行的建议',
    '复杂研判可以要求区分事实、推断和不确定性'
  ],
  report: [
    '告诉我报告受众、篇幅和用途，我会调整结构与专业程度',
    '有固定模板时直接上传，可以减少后续版式调整'
  ],
  chart: [
    '说明图表类型、单位和重点指标，可以让表达更准确',
    '需要用于汇报时，可以同时指定尺寸、配色和导出格式'
  ],
  ppt: [
    '说明演示对象、页数和汇报时长，有助于控制内容密度',
    '提供品牌模板或参考页，可以更快对齐视觉风格'
  ],
  board: [
    '说明节点层级和阅读方向，可以获得更清晰的流程布局',
    '已有草图时可以直接上传，再指定需要保留的结构'
  ],
  ops: [
    '补充故障时间、影响范围和近期变更，有助于快速定位问题',
    '执行高风险操作前，可以要求先给出处置和回退步骤'
  ]
})

const DEFAULT_STATUS_BY_MODE = Object.freeze({
  assistant: '正在理解需求并规划处理步骤',
  query: '正在准备查询和核验数据',
  knowledge: '正在定位相关知识和依据',
  expert: '正在组织专业分析思路',
  report: '正在规划报告结构和内容',
  chart: '正在分析数据的表达方式',
  ppt: '正在规划演示结构和重点',
  board: '正在梳理节点关系和布局',
  ops: '正在分析现象和影响范围'
})

const TOOL_STATUS_RULES = Object.freeze([
  { pattern: /(search|browse|web|retriev|knowledge)/i, label: '正在检索并核验相关资料' },
  { pattern: /(query|sql|database|dataset|monitor|forecast)/i, label: '正在查询并核验数据' },
  { pattern: /(chart|echarts|visual|plot|image)/i, label: '正在生成可视化结果' },
  { pattern: /(report|document|docx|pdf|ppt|slide)/i, label: '正在组织交付内容' },
  { pattern: /(read|file|attachment|resource)/i, label: '正在读取任务资料' },
  { pattern: /(write|save|export|download)/i, label: '正在整理任务成果' },
  { pattern: /(weather|meteorolog)/i, label: '正在分析气象条件' },
  { pattern: /(gis|map|spatial|station)/i, label: '正在处理空间信息' },
  { pattern: /(expert|sub.?agent|workflow|delegate)/i, label: '正在协调专业分析' }
])

function normalizeAgentMode(agentMode) {
  const mode = String(agentMode || 'assistant').toLowerCase()
  return Object.keys(MODE_TIPS).find(candidate => mode === candidate || mode.startsWith(`${candidate}_`)) || 'assistant'
}

export function getAgentProgressStatus(items = [], agentMode = 'assistant') {
  const latest = items.at(-1)
  if (!latest) return DEFAULT_STATUS_BY_MODE[normalizeAgentMode(agentMode)]
  if (latest.kind === 'thought') return '正在梳理分析思路'
  if (latest.kind !== 'tool') return '正在推进任务'
  if (latest.status === 'error') return '正在调整执行方式并继续处理'
  if (latest.status === 'done' || latest.status === 'called') return '已找到一批线索，正在继续核验'
  const toolName = String(latest.toolName || '')
  return TOOL_STATUS_RULES.find(rule => rule.pattern.test(toolName))?.label || '正在执行分析步骤'
}

export function getAgentProgressTips(agentMode = 'assistant') {
  return [...MODE_TIPS[normalizeAgentMode(agentMode)], ...GENERAL_TIPS]
}

export function selectAgentProgressTip(agentMode, rotationIndex, seed = 0) {
  const tips = getAgentProgressTips(agentMode)
  if (!tips.length) return ''
  const index = (Math.max(0, rotationIndex) + Math.abs(seed)) % tips.length
  return tips[index]
}

export function formatRunningElapsed(elapsedSeconds) {
  const totalSeconds = Math.max(0, Math.floor(Number(elapsedSeconds) || 0))
  if (totalSeconds < 60) return `已进行 ${totalSeconds} 秒`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds ? `已进行 ${minutes} 分 ${seconds} 秒` : `已进行 ${minutes} 分`
}
