import test from 'node:test'
import assert from 'node:assert/strict'

import {
  COMMAND_CENTER_SCENES,
  COMMAND_CENTER_WORKSPACES,
  getCommandCenterRevealLevel,
  getCommandCenterWorkspace,
  nextCommandCenterScene,
  resolveCommandCenterScene
} from '../coordinator/commandCenterDemo.js'

test('voice intents move the command center through the demo story', () => {
  assert.equal(resolveCommandCenterScene('展开源创包装厂房站点异常'), COMMAND_CENTER_SCENES.ANOMALY)
  assert.equal(resolveCommandCenterScene('这个问题可能是什么原因？'), COMMAND_CENTER_SCENES.DIAGNOSIS)
  assert.equal(resolveCommandCenterScene('附近有没有可以到站处理的人员？'), COMMAND_CENTER_SCENES.STAFFING)
  assert.equal(resolveCommandCenterScene('为源创包装厂房站点生成任务草案'), COMMAND_CENTER_SCENES.TASK_DRAFT)
  assert.equal(resolveCommandCenterScene('不要只看这个站，展示全省运维情况'), COMMAND_CENTER_SCENES.PROVINCE)
  assert.equal(resolveCommandCenterScene('分析全省智慧运维调度'), COMMAND_CENTER_SCENES.MOBILITY)
  assert.equal(resolveCommandCenterScene('看看运维单位和运维人员的轨迹'), COMMAND_CENTER_SCENES.MOBILITY)
  assert.equal(resolveCommandCenterScene('哪些站点频繁到站'), COMMAND_CENTER_SCENES.MOBILITY)
  assert.equal(resolveCommandCenterScene('分析一下跨市运维任务'), COMMAND_CENTER_SCENES.MOBILITY)
  assert.equal(resolveCommandCenterScene('看看是否实现了最优资源调配'), COMMAND_CENTER_SCENES.MOBILITY)
  assert.equal(resolveCommandCenterScene('给出综合资源优化建议'), COMMAND_CENTER_SCENES.MOBILITY)
  assert.equal(resolveCommandCenterScene('识别外部环境干扰'), COMMAND_CENTER_SCENES.INTERFERENCE)
  assert.equal(resolveCommandCenterScene('视频发现喷淋雾炮'), COMMAND_CENTER_SCENES.INTERFERENCE)
  assert.equal(resolveCommandCenterScene('筛选告警并进行时空关联'), COMMAND_CENTER_SCENES.INTERFERENCE_CORRELATION)
  assert.equal(resolveCommandCenterScene('判断是否影响监测代表性'), COMMAND_CENTER_SCENES.INTERFERENCE_IMPACT)
  assert.equal(resolveCommandCenterScene('生成干扰证据包和处置草案'), COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE)
  assert.equal(resolveCommandCenterScene('恢复今日值守总览'), COMMAND_CENTER_SCENES.OVERVIEW)
})

test('unknown voice intent keeps the current large-screen context', () => {
  assert.equal(
    resolveCommandCenterScene('把这部分再讲清楚', COMMAND_CENTER_SCENES.DIAGNOSIS),
    COMMAND_CENTER_SCENES.DIAGNOSIS
  )
})

test('three demo stories grow four persistent workspaces instead of navigating dashboard pages', () => {
  assert.equal(getCommandCenterWorkspace(COMMAND_CENTER_SCENES.OVERVIEW), COMMAND_CENTER_WORKSPACES.AMBIENT)
  assert.equal(getCommandCenterWorkspace(COMMAND_CENTER_SCENES.ANOMALY), COMMAND_CENTER_WORKSPACES.INVESTIGATION)
  assert.equal(getCommandCenterWorkspace(COMMAND_CENTER_SCENES.TASK_DRAFT), COMMAND_CENTER_WORKSPACES.INVESTIGATION)
  assert.equal(getCommandCenterWorkspace(COMMAND_CENTER_SCENES.PROVINCE), COMMAND_CENTER_WORKSPACES.MOBILITY)
  assert.equal(getCommandCenterWorkspace(COMMAND_CENTER_SCENES.INTERFERENCE), COMMAND_CENTER_WORKSPACES.INTERFERENCE)
  assert.equal(getCommandCenterWorkspace(COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE), COMMAND_CENTER_WORKSPACES.INTERFERENCE)
  assert.equal(getCommandCenterRevealLevel(COMMAND_CENTER_SCENES.ANOMALY), 1)
  assert.equal(getCommandCenterRevealLevel(COMMAND_CENTER_SCENES.DIAGNOSIS), 2)
  assert.equal(getCommandCenterRevealLevel(COMMAND_CENTER_SCENES.STAFFING), 3)
  assert.equal(getCommandCenterRevealLevel(COMMAND_CENTER_SCENES.TASK_DRAFT), 4)
  assert.equal(getCommandCenterRevealLevel(COMMAND_CENTER_SCENES.INTERFERENCE), 1)
  assert.equal(getCommandCenterRevealLevel(COMMAND_CENTER_SCENES.INTERFERENCE_CORRELATION), 2)
  assert.equal(getCommandCenterRevealLevel(COMMAND_CENTER_SCENES.INTERFERENCE_IMPACT), 3)
  assert.equal(getCommandCenterRevealLevel(COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE), 4)
})

test('presenter navigation is clamped to the demo sequence', () => {
  assert.equal(nextCommandCenterScene(COMMAND_CENTER_SCENES.OVERVIEW, -1), COMMAND_CENTER_SCENES.OVERVIEW)
  assert.equal(nextCommandCenterScene(COMMAND_CENTER_SCENES.OVERVIEW, 1), COMMAND_CENTER_SCENES.ALERT)
  assert.equal(nextCommandCenterScene(COMMAND_CENTER_SCENES.MOBILITY, 1), COMMAND_CENTER_SCENES.INTERFERENCE)
  assert.equal(nextCommandCenterScene(COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE, 1), COMMAND_CENTER_SCENES.INTERFERENCE_PACKAGE)
})
