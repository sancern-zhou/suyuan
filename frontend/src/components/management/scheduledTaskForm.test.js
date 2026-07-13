import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildTaskPayload,
  selectableWeixinUsers
} from './scheduledTaskForm.js'


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
