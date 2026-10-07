import test from 'node:test'
import assert from 'node:assert/strict'

import {
  followsStructuredQuestion,
  getStructuredQuestionForFinal,
  isWaitingForAgentResponse
} from './messageProcessGrouping.js'

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

test('identifies a question handoff from its paired tool result across the follow-up', () => {
  const messages = [
    { id: 'u1', type: 'user', content: '测试工具' },
    { id: 'call', type: 'tool_use', data: { tool_use_id: 't1', tool_name: 'ask_user_question' } },
    {
      id: 'result', type: 'tool_result',
      data: {
        tool_use_id: 't1', tool_name: 'ask_user_question',
        result: { metadata: { interaction_required: {
          kind: 'structured_question', questions: [{ question: '选择格式？' }]
        } } }
      }
    },
    { id: 'waiting', type: 'final', content: '已暂停，等待用户回答后继续。' },
    { id: 'reply', type: 'final', content: '已收到选择。' },
    { id: 'later', type: 'final', content: '其他回复。' }
  ]
  assert.equal(getStructuredQuestionForFinal(messages[3], messages).questions[0].question, '选择格式？')
  assert.equal(followsStructuredQuestion(messages[4], messages), true)
  assert.equal(followsStructuredQuestion(messages[5], messages), false)
})
