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
      'M5 5.5h11a3 3 0 0 1 3 3V14a3 3 0 0 1-3 3H10l-4.5 3v-3.3A3 3 0 0 1 3 14V8.5a3 3 0 0 1 2-3Z',
      'm14.8 3 .55 1.45 1.45.55-1.45.55L14.8 7l-.55-1.45L12.8 5l1.45-.55.55-1.45Z',
      'M7.5 10.5h7M7.5 13.5h4.5'
    ]
  },
  {
    id: 'ppt',
    name: '幻灯片智能体',
    shortName: '幻灯片',
    description: '创建、检查并多轮完善高质量可编辑演示文稿',
    welcome: {
      description: '围绕演示目标规划内容结构与视觉表达，生成可继续编辑的 PPTX，并在原文件基础上反复修改完善。',
      features: [
        '规划演示逻辑、页面结构与重点信息',
        '生成包含原生文本、图表和图形的可编辑幻灯片',
        '基于已有源码项目定位页面并进行增量修改',
        '检查内容溢出、布局质量与文件完整性'
      ],
      example: '例如："根据我上传的项目材料制作一份 10 页汇报 PPT，并采用蓝色科技风"'
    },
    tags: ['可编辑 PPT', '演示设计'],
    accent: '#5b6de8',
    iconPaths: [
      'M3.5 4.5h17v12h-17z',
      'M8 20.5h8M12 16.5v4',
      'm7 12 3-3 2.5 2 4-4',
      'M16.5 7.5v3h-3'
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
      'M12 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
      'M5.5 18.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM18.5 18.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
      'm10.2 10.5-2.8 3.2M13.8 10.5l2.8 3.2M8.5 18.5h7'
    ]
  },
  {
    id: 'query',
    name: 'AI问数智能体',
    shortName: '问数',
    description: '自然语言查询数据并完成统计分析',
    welcome: {
      description: '通过自然语言查询结构化数据，快速完成统计、对比和结论整理。',
      features: [
        '查询空气质量、气象和监测站点等业务数据',
        '完成统计汇总、同比环比和排名分析',
        '将查询结果整理为清晰的表格和结论',
        '保留可追溯的数据来源与查询口径'
      ],
      example: '例如："查询广州本月 PM2.5 日均浓度，并与去年同期对比"'
    },
    tags: ['数据查询', '统计分析'],
    accent: '#0b9b8a',
    iconPaths: [
      'M5 6c0 1.7 3.1 3 7 3s7-1.3 7-3-3.1-3-7-3-7 1.3-7 3Z',
      'M5 6v5c0 1.7 3.1 3 7 3 1.2 0 2.3-.1 3.2-.4',
      'M5 11v5c0 1.7 3.1 3 7 3',
      'M18 14.5a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm2.2 5.2 1.8 1.8'
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
      'M5 3.5h9l4 4V20H5V3.5Z',
      'M14 3.5v4h4M8 10h5M8 13h4',
      'm10 18 6.4-6.4a1.4 1.4 0 0 1 2 2L12 20l-2.8.7.8-2.7Z'
    ]
  },
  {
    id: 'chart',
    name: '图表创作智能体',
    shortName: '图表',
    description: '生成数据图表及专题可视化内容',
    welcome: {
      description: '根据数据结构和表达目标创作清晰、准确的专业图表，让趋势、对比和业务关系更直观。',
      features: [
        '识别数据特征并推荐合适的图表类型',
        '生成趋势、对比、分布、地图和专题图表',
        '输出 ECharts 与适合报告使用的静态图表',
        '调整配色、标题、标注和整体版式'
      ],
      example: '例如："绘制广州各站点 PM2.5 月均浓度对比图，并突出异常站点"'
    },
    tags: ['数据图表', '流程图'],
    accent: '#d24d77',
    iconPaths: [
      'M4 4.5v15h16',
      'm5 16 4-5 4 3 6-8',
      'M9 11a1 1 0 1 0 0 .01M13 14a1 1 0 1 0 0 .01M19 6a1 1 0 1 0 0 .01'
    ]
  },
  {
    id: 'board',
    name: '画板创作智能体',
    shortName: '画板',
    description: '创建和编辑可交互的流程图与结构化画板',
    welcome: {
      description: '根据文字、文档或参考图片创建可继续编辑的 draw.io 画板，并精确处理节点、连线和布局。',
      features: [
        '创建业务流程图、架构图和关系图',
        '基于当前画板局部修改节点、连线与样式',
        '结合截图检查视觉效果和结构差异',
        '保留可编辑 XML 与画板版本状态'
      ],
      example: '例如："阅读我上传的任务说明，绘制一张三模块业务流程画板"'
    },
    tags: ['流程画板', '可编辑图形'],
    accent: '#7b61d1',
    iconPaths: [
      'M4.5 4.5h5v5h-5zM14.5 4.5h5v5h-5zM9.5 14.5h5v5h-5z',
      'M9.5 7h5M7 9.5v3a4.5 4.5 0 0 0 4.5 4.5M17 9.5v3a4.5 4.5 0 0 1-4.5 4.5'
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
      'M14.6 6.2a4 4 0 0 0-5.1 5.1L4 16.8a1.8 1.8 0 0 0 2.5 2.5l5.5-5.5a4 4 0 0 0 5.1-5.1l-2.4 2.4-2.5-.7-.7-2.5 3.1-1.7Z',
      'M17.5 14.5v2M17.5 20v.5M14.5 17.5h-2M20.5 17.5h1',
      'M15.4 15.4 14 14M19.6 19.6 21 21M19.6 15.4 21 14M15.4 19.6 14 21'
    ]
  }
])

export const AGENT_MODE_IDS = Object.freeze(AGENT_MODES.map(agent => agent.id))

export const AGENT_SCENES = Object.freeze([
  {
    id: 'office',
    name: '办公',
    description: '日常办公与内容创作',
    modeIds: ['assistant', 'ppt', 'board'],
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
    modeIds: ['query', 'expert', 'report', 'chart'],
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

export const selectAgentModes = modeIds => modeIds.map(getAgentMode).filter(Boolean)
