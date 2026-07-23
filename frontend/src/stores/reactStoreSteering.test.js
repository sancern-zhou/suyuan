import test from 'node:test'
import assert from 'node:assert/strict'

import {
  addPendingSteeringInput,
  applyPendingSteeringInputs,
  fallbackSteeringInputToQueue,
  promoteUnappliedSteeringInputsToQueue
} from './reactStoreSteering.js'


test('promotes repeated identical steering inputs as distinct queued turns', () => {
  const state = { pendingSteeringInputs: [], pendingUserInputs: [], messages: [] }
  addPendingSteeringInput(state, '重复指令', '2026-07-20T00:00:00Z')
  addPendingSteeringInput(state, '重复指令', '2026-07-20T00:00:01Z')

  const promoted = promoteUnappliedSteeringInputsToQueue(state)

  assert.equal(promoted, 2)
  assert.equal(state.pendingUserInputs.length, 2)
  assert.equal(state.messages.length, 2)
  assert.notEqual(
    state.pendingUserInputs[0].clientMessageId,
    state.pendingUserInputs[1].clientMessageId
  )
})


test('records applied steering once in the visible transcript', () => {
  const state = { pendingSteeringInputs: [], pendingUserInputs: [], messages: [] }
  addPendingSteeringInput(state, '改成表格', '2026-07-20T00:00:00Z')

  assert.equal(
    applyPendingSteeringInputs(state, ['改成表格'], '2026-07-20T00:00:02Z'),
    1
  )
  assert.deepEqual(
    state.messages.map(message => ({
      type: message.type,
      content: message.content,
      steering: message.steering,
      steeringStatus: message.steeringStatus
    })),
    [{
      type: 'user',
      content: '改成表格',
      steering: true,
      steeringStatus: 'applied'
    }]
  )

  applyPendingSteeringInputs(state, ['改成表格'], '2026-07-20T00:00:03Z')
  assert.equal(state.messages.length, 1)
})


test('does not queue twice when completion promotion wins the steer response race', () => {
  const state = { pendingSteeringInputs: [], pendingUserInputs: [], messages: [] }
  const steeringInputId = addPendingSteeringInput(
    state,
    '临界追加',
    '2026-07-20T00:00:00Z'
  )
  promoteUnappliedSteeringInputsToQueue(state)

  fallbackSteeringInputToQueue(state, '临界追加', steeringInputId)

  assert.equal(state.pendingUserInputs.length, 1)
  assert.equal(state.messages.length, 1)
  assert.equal(state.pendingUserInputs[0].clientMessageId, `queued_${steeringInputId}`)
})


test('reconciles identical steering inputs by id instead of content', () => {
  const state = { pendingSteeringInputs: [], pendingUserInputs: [], messages: [] }
  const firstId = addPendingSteeringInput(state, '相同内容', '2026-07-20T00:00:00Z')
  const secondId = addPendingSteeringInput(state, '相同内容', '2026-07-20T00:00:01Z')

  applyPendingSteeringInputs(
    state,
    ['相同内容'],
    '2026-07-20T00:00:02Z',
    [secondId]
  )

  assert.deepEqual(state.pendingSteeringInputs.map(item => item.id), [firstId])
  assert.equal(state.messages[0].steeringInputId, secondId)
})
