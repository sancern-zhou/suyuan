import test from 'node:test'
import assert from 'node:assert/strict'

import { isAgentModeRunning, resolveAgentSelection } from './workspacePolicy.js'

const createState = () => ({
  modeStates: {
    assistant: { isAnalyzing: false },
    expert: { isAnalyzing: false }
  },
  sessionStates: {}
})

test('idle mode selection requests a fresh conversation', () => {
  assert.deepEqual(resolveAgentSelection('assistant', createState()), {
    mode: 'assistant',
    action: 'reset-and-open'
  })
})

test('running mode selection preserves the active mode state', () => {
  const state = createState()
  state.modeStates.expert.isAnalyzing = true

  assert.equal(isAgentModeRunning('expert', state), true)
  assert.deepEqual(resolveAgentSelection('expert', state), {
    mode: 'expert',
    action: 'open-running'
  })
})

test('running session selection preserves background task state', () => {
  const state = createState()
  state.sessionStates.expert_session_1 = {
    mode: 'expert',
    isAnalyzing: true
  }

  assert.equal(isAgentModeRunning('expert', state), true)
  assert.equal(resolveAgentSelection('expert', state).action, 'open-running')
})

test('unsupported mode selection is rejected', () => {
  assert.deepEqual(resolveAgentSelection('missing', createState()), {
    mode: 'missing',
    action: 'invalid'
  })
})
