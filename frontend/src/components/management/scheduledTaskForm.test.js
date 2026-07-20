import assert from 'node:assert/strict'
import test from 'node:test'

import {
  applyExecutionMode,
  applyTriggerDefaults,
  buildTaskPayload,
  selectableWeixinUsers
} from './scheduledTaskForm.js'


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
