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
      'M4 5h16v12H4z',
      'M8 21h8',
      'M12 17v4',
      'm9 13 3-5 3 5'
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
      'M5 19V5',
      'M5 19h14',
      'M9 16v-5',
      'M13 16V8',
      'M17 16v-3'
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
      'M4 5h16v14H4z',
      'M7 9h4v3H7z',
      'M13 12h4v3h-4z',
      'M11 10.5h2v3h-2'
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

export const AGENT_PLATFORM_MODE_IDS = Object.freeze([
  'query',
  'expert',
  'report',
  'chart'
])

export const AGENT_PLATFORM_AGENTS = Object.freeze(
  AGENT_PLATFORM_MODE_IDS.map(mode => AGENT_MODES.find(agent => agent.id === mode))
)

export const getAgentMode = mode => AGENT_MODES.find(agent => agent.id === mode) || null
