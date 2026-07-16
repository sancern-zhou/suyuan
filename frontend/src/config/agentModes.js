export const AGENT_MODES = Object.freeze([
  {
    id: 'assistant',
    name: '通用助手智能体',
    shortName: '助手',
    description: '通用问答、任务处理与综合分析',
    welcome: {
      description: '面向日常办公、信息整理和综合任务处理，为你提供从需求理解到成果交付的一站式协助。',
      features: [
        '解答通用问题，梳理需求与工作思路',
        '处理文件、表格、文档和演示材料',
        '拆解复杂任务，汇总并提炼关键信息',
        '形成清晰、可直接使用的内容成果'
      ],
      example: '例如："整理我上传的项目材料，提炼关键结论并生成一份汇报提纲"'
    },
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
    welcome: {
      description: '面向复杂的大气环境问题组织多领域专家协同分析，综合数据、机理与业务经验形成专业判断。',
      features: [
        '协同开展空气质量、气象和污染组分分析',
        '诊断污染过程成因、传输路径与关键影响因素',
        '交叉核验多类证据，识别结论的不确定性',
        '输出专业研判结论与针对性决策建议'
      ],
      example: '例如："综合分析广州近期臭氧污染过程的成因，并给出管控建议"'
    },
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
    welcome: {
      description: '将业务资料、分析结论和图表组织为结构清晰、内容完整且便于继续编辑的专业报告。',
      features: [
        '按报告目标规划章节结构与内容重点',
        '整合对话结论、上传资料和可视化图表',
        '依据模板生成简报、专报和分析报告',
        '优化表述与版式，形成可编辑交付成果'
      ],
      example: '例如："根据本轮分析结果生成一份污染过程溯源简报"'
    },
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
    welcome: {
      description: '根据数据结构和表达目标创作清晰、准确的专业图表，让趋势、对比和业务关系更直观。',
      features: [
        '识别数据特征并推荐合适的图表类型',
        '生成趋势、对比、分布、地图和专题图表',
        '创作流程图、关系图等结构化视觉内容',
        '调整配色、标题、标注和整体版式'
      ],
      example: '例如："绘制广州各站点 PM2.5 月均浓度对比图，并突出异常站点"'
    },
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
    welcome: {
      description: '面向系统运维与工单处置场景，协助定位故障原因、评估影响并形成可执行的处理方案。',
      features: [
        '解析运维工单，提取故障现象与影响范围',
        '结合日志和运行状态排查潜在根因',
        '制定处置步骤、验证方法和回退方案',
        '沉淀处理记录与可复用的运维经验'
      ],
      example: '例如："审核这个月1-7日的运维工单"'
    },
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
    modeIds: ['assistant', 'chart'],
    iconPaths: [
      { tone: 'primary', d: 'M5 3.5h9l4 4V20H5V3.5Z' },
      { tone: 'primary', d: 'M14 3.5v4h4' },
      { tone: 'primary', d: 'M8 9.5h4M8 13h3' },
      { tone: 'accent', d: 'm10.5 17.5 5.9-5.9a1.4 1.4 0 0 1 2 2l-5.9 5.9-2.8.7.8-2.7Z' }
    ]
  },
  {
    id: 'monitoring',
    name: '监测分析',
    description: '环境数据研判与成果输出',
    modeIds: ['query', 'expert', 'report'],
    iconPaths: [
      { tone: 'primary', d: 'M4 5v14h16' },
      { tone: 'primary', d: 'm6.5 14 3-3 3 2 3.5-6 3 2' },
      { tone: 'accent', d: 'M8.5 11a1 1 0 1 0 2 0 1 1 0 0 0-2 0ZM15 7a1 1 0 1 0 2 0 1 1 0 0 0-2 0ZM18 9a1 1 0 1 0 2 0 1 1 0 0 0-2 0Z' }
    ]
  },
  {
    id: 'operations',
    name: '运维管理',
    description: '运维处置与任务管理',
    modeIds: ['ops'],
    iconPaths: [
      { tone: 'primary', d: 'm12 3.5 7.4 4.25v8.5L12 20.5l-7.4-4.25v-8.5L12 3.5Z' },
      { tone: 'primary', d: 'M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z' },
      { tone: 'accent', d: 'm10.3 12 1.15 1.15 2.4-2.55' },
      { tone: 'accent', d: 'M18.3 5.2a1.1 1.1 0 1 0 2.2 0 1.1 1.1 0 0 0-2.2 0Z' }
    ]
  }
])

export const getAgentMode = mode => AGENT_MODES.find(agent => agent.id === mode) || null
