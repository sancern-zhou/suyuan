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
    name: '问数生图智能体',
    shortName: '问数生图',
    description: '自然语言查询数据、统计分析并生成专业图表',
    welcome: {
      description: '通过自然语言查询结构化数据，或使用你手动提供的数据，完成统计分析并生成专业图表。',
      features: [
        '查询空气质量、气象和监测站点等业务数据',
        '完成统计汇总、同比环比和排名分析',
        '将查询结果或手动输入数据生成交互式与静态图表',
        '保留可追溯的数据来源、查询口径和图表产物'
      ],
      example: '例如："查询江苏本月 PM2.5 日均浓度，与去年同期对比并生成趋势图"'
    },
    tags: ['数据查询', '图表生成'],
    accent: '#0b9b8a',
    iconPaths: [
      'M5 6c0 1.7 3.1 3 7 3s7-1.3 7-3-3.1-3-7-3-7 1.3-7 3Z',
      'M5 6v5c0 1.7 3.1 3 7 3 1.2 0 2.3-.1 3.2-.4',
      'M5 11v5c0 1.7 3.1 3 7 3',
      'M18 14.5a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm2.2 5.2 1.8 1.8'
    ]
  },
  {
    id: 'knowledge',
    name: '知识问答智能体',
    shortName: '知识问答',
    description: '检索授权知识库，快速提供有依据的专业回答',
    welcome: {
      description: '面向制度、标准、业务资料和专业文档进行快速问答，从授权知识库中定位依据并给出可追溯答案。',
      features: [
        '检索共享、本地及个人知识库中的相关资料',
        '回答制度条款、标准规范和业务知识问题',
        '结合原文上下文核验关键数字与重要结论',
        '标明知识库和文档来源，识别资料冲突与缺口'
      ],
      example: '例如："根据知识库说明，重污染天气应急响应的启动条件是什么？"'
    },
    tags: ['知识检索', '来源追溯'],
    accent: '#237a57',
    iconPaths: [
      'M4.5 4.5h6.2A3.3 3.3 0 0 1 14 7.8v11.7H7.8a3.3 3.3 0 0 0-3.3 0v-15Z',
      'M19.5 4.5h-2.2A3.3 3.3 0 0 0 14 7.8v11.7h2.2a3.3 3.3 0 0 1 3.3 0v-15Z',
      'M7.5 9h3M7.5 12h3M16.5 9h1'
    ]
  },
  {
    id: 'jiangsu_query',
    name: '江苏问数智能体',
    shortName: '江苏问数',
    description: '查询江苏省站点监测数据并完成统计分析',
    welcome: {
      description: '面向江苏省空气监测站数据，以自然语言完成小时、日均和5分钟数据查询、比较与趋势分析。',
      features: [
        '查询江苏省站点小时、日均和5分钟监测数据',
        '区分原始/审核、工况/标况等数据口径',
        '完成趋势、对比、统计与异常线索整理',
        '保留站点编码、时间范围和数据来源等证据'
      ],
      example: '例如：“查询1002A站点昨天的小时 PM2.5 与臭氧趋势”'
    },
    tags: ['江苏数据', '站点查询'],
    accent: '#1677b8',
    iconPaths: [
      'M4 5.5h16v13H4zM7 15l3-3 2.5 2 4.5-5',
      'M7 9h.01M12 9h.01M17 9h.01',
      'M5.5 20h13'
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
  },
  {
    id: 'smart_inspection',
    name: '智能巡检智能体',
    shortName: '智能巡检',
    description: '巡查站点告警线索，辅助形成巡检与工单派发建议',
    welcome: {
      description: '面向站点巡检与工单闭环场景，先基于运维告警记录识别需关注站点、梳理巡检重点，并形成待人工确认的工单建议。',
      features: [
        '按站点、时间和告警状态查询运维告警/电话记录',
        '梳理异常线索、影响范围和优先巡检对象',
        '生成包含巡检项与处置建议的工单草案',
        '当前仅做查询与建议，不会创建、派发或关闭工单'
      ],
      example: '例如：“查询昨天5006A、5005A的未处理告警，并生成巡检工单建议”'
    },
    tags: ['站点巡检', '工单建议'],
    accent: '#1f8f72',
    iconPaths: [
      'M5 4.5h14v15H5zM8 8h5M8 11.5h8M8 15h5',
      'm14.5 17.5 1.7 1.7 3.3-3.7',
      'M17.5 4.5v-2M20.5 6.5h2M14.5 6.5h-2'
    ]
  },
  {
    id: 'operations_analysis',
    name: '运维操作分析智能体',
    shortName: '操作分析',
    description: '分析人员到站覆盖与空间分布，发现值得管理核查的运维模式',
    welcome: {
      description: '面向运维管理人员，结合人员到站签到和站点空间台账，发现跨市频繁到站、覆盖失衡与疑似不经济的到站顺序，并给出待核查的优化建议。',
      features: [
        '按人员、单位、站点和时间查询到站签到记录',
        '结合站点城市与位置梳理人员覆盖和跨市到站模式',
        '识别值得管理人员进一步核查的高频远距离或重复折返线索',
        '当前不判定工单或告警流程合规，也不作自动考核结论'
      ],
      example: '例如：“分析本月运维人员的跨市到站情况，找出值得核查的路径模式”'
    },
    tags: ['人员覆盖', '路径洞察'],
    accent: '#b36a28',
    iconPaths: [
      'M5 19.5V7.5l7-4 7 4v12M8 10.5h.01M12 8.5h.01M16 10.5h.01M10 19.5v-4h4v4',
      'M3.5 5.5c3 0 3 4 6 4s3-4 6-4 3 4 5 4',
      'M18.5 15.5a2.5 2.5 0 1 0 0 .01Z'
    ]
  },
  {
    id: 'device_control',
    name: '设备反控智能体',
    shortName: '设备反控',
    description: '在人工确认下查询并执行受限的站房设备反控指令',
    welcome: {
      description: '面向已授权站点，查询质控设备状态并生成受控的阀门、电源或空调指令；每次执行前都会展示目标与动作，须经人工明确确认。',
      features: [
        '读取质控阀、零气机、动态校准仪及子站空调状态',
        '仅支持审核通过的固定设备动作和空调设定范围',
        '执行前生成待确认指令，执行后自动复查状态',
        '记录会话、指令、结果与复查信息，便于追溯'
      ],
      example: '例如：“查询站点唯一编号 320100001 的设备状态，并准备将空调设为制冷 24℃”'
    },
    tags: ['设备反控', '人工确认'],
    accent: '#b54738',
    iconPaths: [
      'M4.5 8.5h15v10h-15zM8 8.5V5h8v3.5M8 13.5h.01M12 13.5h.01M16 13.5h.01',
      'M12 18.5v2M9 20.5h6',
      'm16 5 2 2-3 3-2-2 3-3Z'
    ]
  },
  {
    id: 'station_fault_diagnosis',
    name: '站点故障诊断智能体',
    shortName: '故障诊断',
    description: '汇集告警、监测、巡检和工单证据，研判站点故障并给出处置方案',
    welcome: {
      description: '面向单站故障与数据异常，结合实时告警、监测数据、自动巡检、历史故障工单和知识图谱，输出可追溯的根因研判与现场处置方案。',
      features: [
        '关联站房告警、运维告警和小时/5分钟监测数据',
        '读取自动巡检结果与历史故障工单，识别重复问题',
        '基于知识图谱形成候选根因并标注支持与反证',
        '输出处置步骤、验证方法、风险提示和回退建议，不直接控制设备'
      ],
      example: '例如：“诊断站点 1002A 今天上午的断数故障，并给出现场排查方案”'
    },
    tags: ['站点故障', '根因诊断'],
    accent: '#8a3ffc',
    iconPaths: [
      'M4.5 5.5h15v13h-15zM8 9.5h8M8 13h4',
      'M17.5 16.5a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm2.1 5.1 1.9 1.9',
      'm12 3 1 2.1L15.2 6l-2.2.9L12 9l-.9-2.1L8.8 6l2.3-.9L12 3Z'
    ]
  }
])

export const AGENT_MODE_IDS = Object.freeze(AGENT_MODES.map(agent => agent.id))

export const AGENT_SCENES = Object.freeze([
  {
    id: 'office',
    name: '办公',
    description: '日常办公与内容创作',
    modeIds: ['assistant', 'knowledge', 'ppt', 'board'],
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
    modeIds: ['query', 'jiangsu_query', 'expert', 'report', 'chart'],
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
    modeIds: ['ops', 'smart_inspection', 'operations_analysis', 'device_control', 'station_fault_diagnosis'],
    iconPaths: [
      { tone: 'primary', d: 'm12 3.5 7.4 4.25v8.5L12 20.5l-7.4-4.25v-8.5L12 3.5Z' },
      { tone: 'primary', d: 'M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z' },
      { tone: 'accent', d: 'm10.3 12 1.15 1.15 2.4-2.55' },
      { tone: 'accent', d: 'M18.3 5.2a1.1 1.1 0 1 0 2.2 0 1.1 1.1 0 0 0-2.2 0Z' }
    ]
  }
])

function mergeAgentMode(agent, override) {
  if (!agent || !override) return agent || null
  return {
    ...agent,
    ...override,
    welcome: override.welcome
      ? {
          ...agent.welcome,
          ...override.welcome,
          features: override.welcome.features || agent.welcome.features
        }
      : agent.welcome,
    tags: override.tags || agent.tags,
    iconPaths: override.iconPaths || agent.iconPaths
  }
}

export const getAgentMode = (mode, overrides = {}) => {
  const agent = AGENT_MODES.find(item => item.id === mode)
  return mergeAgentMode(agent, overrides[mode])
}

export const selectAgentModes = (modeIds, overrides = {}) => (
  modeIds.map(mode => getAgentMode(mode, overrides)).filter(Boolean)
)
