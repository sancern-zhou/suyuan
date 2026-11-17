import test from 'node:test'
import assert from 'node:assert/strict'

import { filterPlatformAgentCards } from './platformCardPolicy.js'

const agents = [
  { id: 'assistant', name: '助手模式' },
  { id: 'query', name: 'AI问数智能体' },
  { id: 'knowledge', name: '知识问答智能体' }
]

test('floating projects hide the assistant card because the floating ball is the unified entry', () => {
  assert.deepEqual(
    filterPlatformAgentCards(agents, { assistantFloating: true }).map(agent => agent.id),
    ['query', 'knowledge']
  )
})

test('projects without the floating feature keep every configured card including assistant', () => {
  assert.deepEqual(filterPlatformAgentCards(agents, { assistantFloating: false }), agents)
  assert.deepEqual(filterPlatformAgentCards(agents), agents)
})
