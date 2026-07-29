import test from 'node:test'
import assert from 'node:assert/strict'

import {
  acknowledgeQueuedInput,
  enqueueUserInput,
  queueIncomingBehindPendingAndTakeNext,
  peekNextQueuedInput,
  takeNextQueuedInput
} from './reactStoreQueue.js'


test('keeps repeated text as distinct FIFO queue entries', () => {
  const state = { pendingUserInputs: [], messages: [] }
  enqueueUserInput(state, { query: '重复' })
  enqueueUserInput(state, { query: '重复' })

  const first = takeNextQueuedInput(state)
  const second = takeNextQueuedInput(state)

  assert.equal(first.query, '重复')
  assert.equal(second.query, '重复')
  assert.notEqual(first.clientMessageId, second.clientMessageId)
  assert.equal(takeNextQueuedInput(state), null)
})


test('preserves structured selection options when dequeuing', () => {
  const state = { pendingUserInputs: [], messages: [] }
  enqueueUserInput(state, {
    query: '',
    options: {
      skillIds: ['skill-1'],
      activeContexts: [{ type: 'skill', id: 'skill-1' }],
      contextRefs: ['file-1']
    }
  })

  const next = takeNextQueuedInput(state)

  assert.deepEqual(next.options.skillIds, ['skill-1'])
  assert.deepEqual(next.options.activeContexts, [{ type: 'skill', id: 'skill-1' }])
  assert.deepEqual(next.options.contextRefs, ['file-1'])
  assert.equal(next.options.queuedAlreadyShown, true)
})


test('puts a new explicit send behind a stranded queue and resumes the oldest item', () => {
  const state = { pendingUserInputs: [], messages: [] }
  enqueueUserInput(state, { query: '旧排队输入' })

  const next = queueIncomingBehindPendingAndTakeNext(state, {
    query: '新输入',
    options: { agentMode: 'assistant' }
  })

  assert.equal(next.query, '旧排队输入')
  assert.deepEqual(state.pendingUserInputs.map(item => item.query), ['旧排队输入', '新输入'])
  assert.deepEqual(state.messages.map(message => message.content), ['旧排队输入', '新输入'])

  assert.equal(acknowledgeQueuedInput(state, next.clientMessageId)?.query, '旧排队输入')
  assert.deepEqual(state.pendingUserInputs.map(item => item.query), ['新输入'])
})


test('does not enqueue an idle send when there is no stranded input', () => {
  const state = { pendingUserInputs: [], messages: [] }

  const next = queueIncomingBehindPendingAndTakeNext(state, { query: '直接发送' })

  assert.equal(next, null)
  assert.equal(state.pendingUserInputs.length, 0)
  assert.equal(state.messages.length, 0)
})


test('peeks without losing a queued turn and acknowledges only the matching id', () => {
  const state = { pendingUserInputs: [], messages: [] }
  enqueueUserInput(state, { query: '第一条' })
  enqueueUserInput(state, { query: '第二条' })

  const first = peekNextQueuedInput(state)

  assert.equal(first.query, '第一条')
  assert.equal(state.pendingUserInputs.length, 2)
  assert.equal(acknowledgeQueuedInput(state, first.clientMessageId)?.query, '第一条')
  assert.deepEqual(state.pendingUserInputs.map(item => item.query), ['第二条'])
})
