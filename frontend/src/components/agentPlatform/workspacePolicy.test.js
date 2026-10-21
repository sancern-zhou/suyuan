import test from 'node:test'
import assert from 'node:assert/strict'

import {
  getRunningAgentSessionId,
  isAgentModeRunning,
  resolveAgentSelection,
  resolveTaskWorkspaceMode
} from './workspacePolicy.js'

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

test('running session lookup ignores an idle active session in the same mode', () => {
  const state = createState()
  state.sessionStates.expert_idle = {
    mode: 'expert',
    isAnalyzing: false
  }
  state.sessionStates.expert_running = {
    mode: 'expert',
    isAnalyzing: true
  }
  state.activeSessionByMode = { expert: 'expert_idle' }

  assert.equal(getRunningAgentSessionId('expert', state), 'expert_running')
})

test('unsupported mode selection is rejected', () => {
  assert.deepEqual(resolveAgentSelection('missing', createState()), {
    mode: 'missing',
    action: 'invalid'
  })
})

test('task workspace selects a supported task agent mode', () => {
  assert.equal(resolveTaskWorkspaceMode({ execution_mode: 'report' }, 'query'), 'report')
})

test('task workspace preserves the current agent for non-chat modes', () => {
  assert.equal(resolveTaskWorkspaceMode({ execution_mode: 'custom' }, 'query'), 'query')
  assert.equal(resolveTaskWorkspaceMode({ execution_mode: 'social' }, 'report'), 'report')
  assert.equal(resolveTaskWorkspaceMode({}, 'query'), 'query')
})
