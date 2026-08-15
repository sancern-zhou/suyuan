import assert from 'node:assert/strict'
import test from 'node:test'

import {
  applyExecutionMode,
  applyTriggerDefaults,
  buildExecutionModeOptions,
  buildTaskPayload,
  selectableWeixinUsers
} from './scheduledTaskForm.js'


test('execution mode options include every project mode plus task-only modes', () => {
  const options = buildExecutionModeOptions([
    { id: 'ops', shortName: '运维' },
    { id: 'jiangsu_query', shortName: '江苏问数' },
    { id: 'station_fault_diagnosis', shortName: '故障诊断' }
  ])

  assert.deepEqual(options.map(option => option.value), [
    'ops',
    'jiangsu_query',
    'station_fault_diagnosis',
    'social',
    'custom'
  ])
  assert.equal(options[1].label, 'jiangsu_query（江苏问数）')
})


test('execution mode options preserve an edited legacy mode without duplicates', () => {
  const options = buildExecutionModeOptions(
    [{ id: 'ops', shortName: '运维' }],
    'expert'
  )

  assert.equal(options.filter(option => option.value === 'expert').length, 1)
  assert.match(options.find(option => option.value === 'expert').label, /当前任务模式/)
})


test('custom payload keeps only unique selected tools in user order', () => {
  const payload = buildTaskPayload({
    name: '最小工具任务',
    description: '生成报告',
    execution_mode: 'custom',
    tool_names: ['write_file', 'read_file', 'write_file', ''],
    trigger_type: 'schedule',
    schedule_type: 'daily_8am',
    enabled: true
  })

  assert.deepEqual(payload.tool_names, ['write_file', 'read_file'])
})


test('non-custom payload omits tools and changing mode clears stale selection', () => {
  const form = { execution_mode: 'custom', tool_names: ['read_file'] }
  applyExecutionMode(form, 'assistant')

  const payload = buildTaskPayload({
    ...form,
    name: '助手任务',
    description: '执行',
    trigger_type: 'schedule',
    schedule_type: 'daily_8am',
    enabled: true
  })

  assert.deepEqual(form.tool_names, [])
  assert.equal(Object.hasOwn(payload, 'tool_names'), false)
})


test('filters active bound WeChat users', () => {
  const users = [
    {
      id: 'a',
      name: 'A',
      status: 'active',
      channel: 'weixin:auto',
      social_user_id: 'weixin:auto:bot:a'
    },
    {
      id: 'b',
      name: 'B',
      status: 'disabled',
      channel: 'weixin:auto',
      social_user_id: 'weixin:auto:bot:b'
    },
    {
      id: 'c',
      name: 'C',
      status: 'active',
      channel: 'qq',
      social_user_id: 'qq:bot:c'
    }
  ]

  assert.deepEqual(selectableWeixinUsers(users).map(user => user.id), ['a'])
})


test('builds an event task with multiple backend user ids', () => {
  const payload = buildTaskPayload({
    name: '运城告警推送',
    description: '生成并推送报告',
    execution_mode: 'social',
    trigger_type: 'event',
    event_type: 'yuncheng.alert.created',
    event_filters: { city: '运城市' },
    broadcast_enabled: true,
    target_user_ids: ['a', 'd'],
    enabled: true,
    tagsText: 'yuncheng,event'
  })

  assert.equal(payload.schedule_type, null)
  assert.deepEqual(payload.target_user_ids, ['a', 'd'])
  assert.deepEqual(payload.event_filters, { city: '运城市' })
  assert.equal(payload.steps[0].retry_on_failure, false)
})


test('keeps schedule fields for schedule tasks', () => {
  const payload = buildTaskPayload({
    name: '日报',
    description: '生成日报',
    execution_mode: 'assistant',
    trigger_type: 'schedule',
    schedule_type: 'daily_custom',
    hour: 9,
    minute: 10,
    broadcast_enabled: false,
    target_user_ids: [],
    enabled: true,
    tagsText: 'daily'
  })

  assert.equal(payload.schedule_type, 'daily_custom')
  assert.equal(payload.hour, 9)
  assert.equal(payload.minute, 10)
  assert.equal(payload.event_type, null)
})


test('schedule and event payloads both preserve selected skill context', () => {
  const schedule = buildTaskPayload({
    name: '定时诊断',
    description: '执行诊断',
    execution_mode: 'expert',
    skill_id: 'sample-skill',
    trigger_type: 'schedule',
    schedule_type: 'daily_8am',
    enabled: true
  })
  const event = buildTaskPayload({
    name: '事件诊断',
    description: '执行诊断',
    execution_mode: 'expert',
    skill_id: 'sample-skill',
    trigger_type: 'event',
    event_type: 'sample.event.created',
    enabled: true
  })

  assert.equal(schedule.skill_id, 'sample-skill')
  assert.equal(event.skill_id, 'sample-skill')
})


test('clearing skill sends null so editing can remove prior injection', () => {
  const payload = buildTaskPayload({
    name: '无 Skill 任务',
    description: '执行',
    skill_id: '',
    trigger_type: 'schedule',
    schedule_type: 'daily_8am',
    enabled: true
  })

  assert.equal(payload.skill_id, null)
})


test('always sends workspace entry state so an existing sidebar entry can be disabled', () => {
  const enabled = buildTaskPayload({
    name: '告警任务',
    description: '执行告警分析',
    trigger_type: 'schedule',
    schedule_type: 'daily_8am',
    workspaceEntryEnabled: true,
    workspaceEntryTitle: '告警溯源'
  })
  const disabled = buildTaskPayload({
    name: '告警任务',
    description: '执行告警分析',
    trigger_type: 'schedule',
    schedule_type: 'daily_8am',
    workspaceEntryEnabled: false,
    workspaceEntryTitle: '告警溯源'
  })

  assert.deepEqual(enabled.workspace_entry, { enabled: true, title: '告警溯源' })
  assert.deepEqual(disabled.workspace_entry, { enabled: false, title: '告警溯源' })
})


test('event trigger defaults to social execution and broadcasting', () => {
  const form = {
    trigger_type: 'schedule',
    execution_mode: 'assistant',
    broadcast_enabled: false,
    event_type: ''
  }

  applyTriggerDefaults(form, 'event', [
    { event_type: 'yuncheng.alert.created' }
  ])

  assert.equal(form.trigger_type, 'event')
  assert.equal(form.execution_mode, 'social')
  assert.equal(form.broadcast_enabled, true)
  assert.equal(form.event_type, 'yuncheng.alert.created')
})
