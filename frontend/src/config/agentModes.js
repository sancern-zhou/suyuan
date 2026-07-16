export const AGENT_MODES = Object.freeze([
  {
    id: 'assistant',
    name: '通用助手智能体',
    shortName: '助手',
    description: '通用问答、任务处理与综合分析',
    tags: ['通用问答', '任务处理'],
    accent: '#2878ff',
    iconPaths: [
      'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
      'M4.5 20a7.5 7.5 0 0 1 15 0'
    ]
  },
  {
    id: 'expert',
    name: '专家分析智能体',
    shortName: '专家',
    description: '多专家协同研判，适合复杂问题和专业决策',
    tags: ['协同研判', '专业决策'],
    accent: '#7656e8',
    iconPaths: [
      'M10 4v5.5l-4.6 7.6A2 2 0 0 0 7.1 20h9.8a2 2 0 0 0 1.7-2.9L14 9.5V4',
      'M8 4h8',
      'M8 15h8'
    ]
  },
  {
    id: 'query',
    name: 'AI问数智能体',
    shortName: '问数',
    description: '自然语言查询数据，联动地图与数据大屏',
    tags: ['数据查询', '地图联动'],
    accent: '#0b9b8a',
    iconPaths: [
      'M4 19V5',
      'M4 19h16',
      'M8 16v-5',
      'M12 16V8',
      'M16 16v-3'
    ]
  },
  {
    id: 'report',
    name: '报告生成智能体',
    shortName: '报告',
    description: '根据资料与分析结果生成结构化专业报告',
    tags: ['专业报告', '结构化输出'],
    accent: '#e78324',
    iconPaths: [
      'M6 3.5h8l4 4v13H6v-17Z',
      'M14 3.5v4h4',
      'M9 12h6',
      'M9 15.5h6'
    ]
  },
  {
    id: 'chart',
    name: '图表创作智能体',
    shortName: '图表',
    description: '生成数据图表、流程图及可视化内容',
    tags: ['数据图表', '流程图'],
    accent: '#d24d77',
    iconPaths: [
      'M5 19V5',
      'M5 19h14',
      'M9 16v-5',
      'M13 16V8',
      'M17 16v-3'
    ]
  },
  {
    id: 'ops',
    name: '运维智能体',
    shortName: '运维',
    description: '处理运维工单、排查问题并辅助形成处置方案',
    tags: ['故障排查', '工单处置'],
    accent: '#52677f',
    iconPaths: [
      'M4 7h16',
      'M6 7v13h12V7',
      'M9 7V4h6v3',
      'M9 12h6',
      'M9 16h4'
    ]
  }
])

export const AGENT_MODE_IDS = Object.freeze(AGENT_MODES.map(agent => agent.id))

export const AGENT_SCENES = Object.freeze([
  {
    id: 'office',
    name: '办公',
    description: '日常办公与内容创作',
    modeIds: ['assistant', 'chart']
  },
  {
    id: 'monitoring',
    name: '监测分析',
    description: '环境数据研判与成果输出',
    modeIds: ['query', 'expert', 'report']
  },
  {
    id: 'operations',
    name: '运维管理',
    description: '运维处置与任务管理',
    modeIds: ['ops']
  }
])

export const getAgentMode = mode => AGENT_MODES.find(agent => agent.id === mode) || null
