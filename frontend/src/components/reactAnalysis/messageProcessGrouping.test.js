import test from 'node:test'
import assert from 'node:assert/strict'

import { isWaitingForAgentResponse } from './messageProcessGrouping.js'

test('shows the thinking placeholder immediately after a user message starts analyzing', () => {
  const messages = [
    { id: 'answer-1', type: 'final', content: '上一轮回复' },
    { id: 'user-2', type: 'user', content: '继续分析' }
  ]

  assert.equal(isWaitingForAgentResponse(messages, true), true)
})

test('hides the thinking placeholder when visible agent output arrives', () => {
  const userMessage = { id: 'user-1', type: 'user', content: '开始分析' }

  for (const type of ['thought', 'tool_use', 'tool_result', 'final', 'assistant', 'error']) {
    assert.equal(
      isWaitingForAgentResponse([userMessage, { id: `agent-${type}`, type }], true),
      false,
      `expected ${type} to replace the placeholder`
    )
  }
})

test('does not show the thinking placeholder outside an active analysis', () => {
  assert.equal(
    isWaitingForAgentResponse([{ id: 'user-1', type: 'user', content: '问题' }], false),
    false
  )
})

test('keeps the placeholder for transport-only start events', () => {
  assert.equal(
    isWaitingForAgentResponse([
      { id: 'user-1', type: 'user', content: '问题' },
      { id: 'start-1', type: 'start', content: '开始分析' }
    ], true),
    true
  )
})
