import assert from 'node:assert/strict'
import { enqueueUserInput, hasShownClientMessage } from './reactStoreQueue.js'

const state = {
  pendingUserInputs: [],
  messages: []
}

const clientMessageId = enqueueUserInput(state, {
  query: '排队执行',
  options: { agentMode: 'report', clientMessageId: 'client_1' }
})

assert.equal(clientMessageId, 'client_1')
assert.equal(state.pendingUserInputs.length, 1)
assert.equal(state.pendingUserInputs[0].clientMessageId, 'client_1')
assert.equal(state.pendingUserInputs[0].options.queuedAlreadyShown, true)
assert.equal(state.messages.length, 1)
assert.equal(state.messages[0].clientMessageId, 'client_1')
assert.equal(state.messages[0].queued, true)
assert.equal(hasShownClientMessage(state, 'client_1'), true)

enqueueUserInput(state, {
  query: '排队执行',
  options: { agentMode: 'report', clientMessageId: 'client_1' }
})

assert.equal(state.pendingUserInputs.length, 1, 'same client message should not be queued twice')
assert.equal(state.messages.length, 1, 'same client message should not be shown twice')

console.log('reactStore queue tests passed')
