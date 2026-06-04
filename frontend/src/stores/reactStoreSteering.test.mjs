import assert from 'node:assert/strict'
import {
  addPendingSteeringInput,
  applyPendingSteeringInputs,
  promoteUnappliedSteeringInputsToQueue
} from './reactStoreSteering.js'

const state = {
  pendingSteeringInputs: [],
  messages: [
    { id: 'u1', type: 'user', content: '开始分析' },
    { id: 't1', type: 'thought', content: '执行工具' }
  ]
}

addPendingSteeringInput(state, '补充考虑昨天数据')

assert.equal(state.pendingSteeringInputs.length, 1)
assert.equal(state.pendingSteeringInputs[0].content, '补充考虑昨天数据')
assert.deepEqual(
  state.messages.map(message => message.id),
  ['u1', 't1'],
  'pending steering input should not be inserted into the message flow'
)

const appliedCount = applyPendingSteeringInputs(state, ['补充考虑昨天数据'], '2026-06-04T12:00:00Z')

assert.equal(appliedCount, 1)
assert.equal(state.pendingSteeringInputs.length, 0)
assert.equal(state.messages.length, 3)
assert.equal(state.messages[2].type, 'user')
assert.equal(state.messages[2].content, '补充考虑昨天数据')
assert.equal(state.messages[2].steering, true)
assert.equal(state.messages[2].steeringStatus, 'applied')

const terminalState = {
  pendingSteeringInputs: [
    { id: 's1', content: '补充生成截图', status: 'pending', timestamp: '2026-06-04T12:01:00Z' }
  ],
  pendingUserInputs: [],
  messages: [
    { id: 'u1', type: 'user', content: '生成演示界面' },
    { id: 'f1', type: 'final', content: '已完成' }
  ]
}

const promotedCount = promoteUnappliedSteeringInputsToQueue(terminalState, {
  agentMode: 'assistant',
  queuedAlreadyShown: true
})

assert.equal(promotedCount, 1)
assert.equal(terminalState.pendingSteeringInputs.length, 0)
assert.equal(terminalState.pendingUserInputs.length, 1)
assert.equal(terminalState.pendingUserInputs[0].query, '补充生成截图')
assert.equal(terminalState.messages[2].type, 'user')
assert.equal(terminalState.messages[2].content, '补充生成截图')
assert.equal(terminalState.messages[2].queued, true)
assert.equal(terminalState.messages[2].steering, false)

const legacyState = {
  pendingSteeringInputs: [],
  pendingUserInputs: [],
  messages: [
    { id: 'u1', type: 'user', content: '开始任务' },
    {
      id: 'legacy_pending',
      type: 'user',
      content: '旧版等待补充',
      steering: true,
      steeringStatus: 'pending'
    },
    { id: 'f1', type: 'final', content: '已完成' }
  ]
}

const legacyPromotedCount = promoteUnappliedSteeringInputsToQueue(legacyState, {
  agentMode: 'assistant',
  queuedAlreadyShown: true
})

assert.equal(legacyPromotedCount, 1)
assert.equal(legacyState.pendingUserInputs[0].query, '旧版等待补充')
assert.equal(legacyState.messages[1].steeringStatus, 'queued')
assert.equal(legacyState.messages[1].queued, true)

console.log('reactStoreSteering tests passed')
