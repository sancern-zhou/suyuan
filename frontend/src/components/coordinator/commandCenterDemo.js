export const COMMAND_CENTER_SCENES = Object.freeze({
  OVERVIEW: 'overview',
  ALERT: 'alert',
  ANOMALY: 'anomaly',
  DIAGNOSIS: 'diagnosis',
  STAFFING: 'staffing',
  TASK_DRAFT: 'task-draft',
  PROVINCE: 'province',
  MOBILITY: 'mobility',
  INTERFERENCE: 'interference',
  INTERFERENCE_CORRELATION: 'interference-correlation',
  INTERFERENCE_IMPACT: 'interference-impact',
  INTERFERENCE_PACKAGE: 'interference-package'
})

export const COMMAND_CENTER_SCENE_SEQUENCE = Object.freeze([
  COMMAND_CENTER_SCENES.OVERVIEW,
  COMMAND_CENTER_SCENES.ALERT,
  COMMAND_CENTER_SCENES.ANOMALY,
  COMMAND_CENTER_SCENES.DIAGNOSIS,
  COMMAND_CENTER_SCENES.STAFFING,
  COMMAND_CENTER_SCENES.TASK_DRAFT,
  COMMAND_CENTER_SCENES.PROVINCE,
  COMMAND_CENTER_SCENES.MOBILITY,
  COMMAND_CENTER_SCENES.INTERFERENCE,
  COMMAND_CENTER_SCENES.INTERFERENCE_CORRELATION,
  COMMAND_CENTER_SCENES.INTERFERENCE_IMPACT,
  COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE
])

export const COMMAND_CENTER_WORKSPACES = Object.freeze({
  AMBIENT: 'ambient',
  INVESTIGATION: 'investigation',
  MOBILITY: 'mobility',
  INTERFERENCE: 'interference'
})

export const COMMAND_CENTER_WORKSPACE_BY_SCENE = Object.freeze({
  [COMMAND_CENTER_SCENES.OVERVIEW]: COMMAND_CENTER_WORKSPACES.AMBIENT,
  [COMMAND_CENTER_SCENES.ALERT]: COMMAND_CENTER_WORKSPACES.AMBIENT,
  [COMMAND_CENTER_SCENES.ANOMALY]: COMMAND_CENTER_WORKSPACES.INVESTIGATION,
  [COMMAND_CENTER_SCENES.DIAGNOSIS]: COMMAND_CENTER_WORKSPACES.INVESTIGATION,
  [COMMAND_CENTER_SCENES.STAFFING]: COMMAND_CENTER_WORKSPACES.INVESTIGATION,
  [COMMAND_CENTER_SCENES.TASK_DRAFT]: COMMAND_CENTER_WORKSPACES.INVESTIGATION,
  [COMMAND_CENTER_SCENES.PROVINCE]: COMMAND_CENTER_WORKSPACES.MOBILITY,
  [COMMAND_CENTER_SCENES.MOBILITY]: COMMAND_CENTER_WORKSPACES.MOBILITY,
  [COMMAND_CENTER_SCENES.INTERFERENCE]: COMMAND_CENTER_WORKSPACES.INTERFERENCE,
  [COMMAND_CENTER_SCENES.INTERFERENCE_CORRELATION]: COMMAND_CENTER_WORKSPACES.INTERFERENCE,
  [COMMAND_CENTER_SCENES.INTERFERENCE_IMPACT]: COMMAND_CENTER_WORKSPACES.INTERFERENCE,
  [COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE]: COMMAND_CENTER_WORKSPACES.INTERFERENCE
})

export const COMMAND_CENTER_REVEAL_LEVEL = Object.freeze({
  [COMMAND_CENTER_SCENES.OVERVIEW]: 0,
  [COMMAND_CENTER_SCENES.ALERT]: 1,
  [COMMAND_CENTER_SCENES.ANOMALY]: 1,
  [COMMAND_CENTER_SCENES.DIAGNOSIS]: 2,
  [COMMAND_CENTER_SCENES.STAFFING]: 3,
  [COMMAND_CENTER_SCENES.TASK_DRAFT]: 4,
  [COMMAND_CENTER_SCENES.PROVINCE]: 1,
  [COMMAND_CENTER_SCENES.MOBILITY]: 2,
  [COMMAND_CENTER_SCENES.INTERFERENCE]: 1,
  [COMMAND_CENTER_SCENES.INTERFERENCE_CORRELATION]: 2,
  [COMMAND_CENTER_SCENES.INTERFERENCE_IMPACT]: 3,
  [COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE]: 4
})

export const COMMAND_CENTER_RESPONSES = Object.freeze({
  [COMMAND_CENTER_SCENES.OVERVIEW]: '已恢复今日值守入口。当前演示聚焦颗粒物数据中断、智慧运维调度和外部环境干扰识别三个场景。',
  [COMMAND_CENTER_SCENES.ALERT]: '发现一项需要优先关注的异常。源创包装厂房站点颗粒物数据自九点十二分起停止更新，建议展开查看。',
  [COMMAND_CENTER_SCENES.ANOMALY]: '我已围绕源创包装厂房异常建立调查上下文，先放入已确认事实，不提前认定故障原因。',
  [COMMAND_CENTER_SCENES.DIAGNOSIS]: '我在当前调查中追加了三个原因假设。采集或传输链路异常的解释力更高，但仍需通信日志和设备状态验证。',
  [COMMAND_CENTER_SCENES.STAFFING]: '我保留了前面的判断依据，并追加两名可到站人员。推荐结果同时考虑距离、相关经验和当前负荷。',
  [COMMAND_CENTER_SCENES.TASK_DRAFT]: '调查上下文已整理为核查任务草案，并携带证据、判断边界和人员建议交给苏小环首页审核。',
  [COMMAND_CENTER_SCENES.PROVINCE]: '我已将工作区切换到全省智慧运维调度，先建立单位、人员、任务和站点需求的资源上下文。',
  [COMMAND_CENTER_SCENES.MOBILITY]: '我已融合近三十日跨市任务、运维单位轨迹、运维人员轨迹和到站记录，识别可合并、属地承接和专项治理的调度机会。',
  [COMMAND_CENTER_SCENES.INTERFERENCE]: '视频模型发现一项疑似喷淋雾炮干扰。我已完成首轮告警筛选，保留视频片段和识别框作为调查起点。',
  [COMMAND_CENTER_SCENES.INTERFERENCE_CORRELATION]: '我已关联事件时间、目标位置、风向风速和监测数据变化。喷淋区域位于站点上风向，时间窗口与颗粒物升高重合。',
  [COMMAND_CENTER_SCENES.INTERFERENCE_IMPACT]: '设备状态和质控记录正常，邻近站点未出现同步变化。当前证据支持外部环境对本站监测代表性产生影响，但仍需人工复核。',
  [COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE]: '视频、监测数据、气象条件、设备状态和运维记录已整理为证据包，并生成现场核查与调度处置草案，等待人工确认。'
})

export function getCommandCenterWorkspace(scene) {
  return COMMAND_CENTER_WORKSPACE_BY_SCENE[scene] || COMMAND_CENTER_WORKSPACES.AMBIENT
}

export function getCommandCenterRevealLevel(scene) {
  return COMMAND_CENTER_REVEAL_LEVEL[scene] || 0
}

const includesAny = (value, terms) => terms.some(term => value.includes(term))

export function resolveCommandCenterScene(query, currentScene = COMMAND_CENTER_SCENES.OVERVIEW) {
  const normalized = String(query || '').trim().toLocaleLowerCase('zh-CN')
  if (!normalized) return currentScene

  if (includesAny(normalized, ['干扰证据包', '生成证据包', '处置草案', '调度处置', '干扰处置'])) {
    return COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE
  }
  if (includesAny(normalized, ['数据影响', '影响判断', '代表性影响', '监测代表性', '是否影响数据'])) {
    return COMMAND_CENTER_SCENES.INTERFERENCE_IMPACT
  }
  if (includesAny(normalized, ['时空关联', '告警筛选', '筛选告警', '关联气象', '关联监测', '关联视频'])) {
    return COMMAND_CENTER_SCENES.INTERFERENCE_CORRELATION
  }
  if (includesAny(normalized, ['外部环境干扰', '人为干扰', '干扰识别', '视频识别', '喷淋', '雾炮', '车辆停靠', '人员靠近', '摄像头遮挡'])) {
    return COMMAND_CENTER_SCENES.INTERFERENCE
  }
  if (includesAny(normalized, ['任务草案', '生成任务', '安排人员', '安排王', '派人', '去处理'])) {
    return COMMAND_CENTER_SCENES.TASK_DRAFT
  }
  if (includesAny(normalized, ['智慧运维', '智慧调度', '运维调度', '综合调度', '单位轨迹', '人员轨迹', '频繁到站', '高频到站', '轨迹', '跨市', '资源调配', '资源配置', '资源优化', '调度分析', '就近派单'])) {
    return COMMAND_CENTER_SCENES.MOBILITY
  }
  if (includesAny(normalized, ['附近', '人员', '到站', '谁可以'])) {
    return COMMAND_CENTER_SCENES.STAFFING
  }
  if (includesAny(normalized, ['全省', '全局', '整体运维', '运维情况'])) {
    return COMMAND_CENTER_SCENES.PROVINCE
  }
  if (includesAny(normalized, ['什么原因', '为什么', '原因分析', '可能原因'])) {
    return COMMAND_CENTER_SCENES.DIAGNOSIS
  }
  if (includesAny(normalized, ['南京', '源创包装', '示范站', '展开异常', '重点异常'])) {
    return COMMAND_CENTER_SCENES.ANOMALY
  }
  if (includesAny(normalized, ['提醒', '主动发现', '新异常'])) {
    return COMMAND_CENTER_SCENES.ALERT
  }
  if (includesAny(normalized, ['返回', '恢复', '今日总览', '值守总览', '首页'])) {
    return COMMAND_CENTER_SCENES.OVERVIEW
  }
  return currentScene
}

export function nextCommandCenterScene(currentScene, direction = 1) {
  const currentIndex = COMMAND_CENTER_SCENE_SEQUENCE.indexOf(currentScene)
  const safeIndex = currentIndex >= 0 ? currentIndex : 0
  const nextIndex = Math.min(
    COMMAND_CENTER_SCENE_SEQUENCE.length - 1,
    Math.max(0, safeIndex + direction)
  )
  return COMMAND_CENTER_SCENE_SEQUENCE[nextIndex]
}
