import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CONVERSATION_LIST_LAYOUT,
  CONVERSATION_LIST_VIEW,
  filterConversationHistory,
  filterSidebarConversations,
  groupSidebarConversationsByMode,
  reconcileConversationHistoryStats,
  resolveConversationAgentMode,
  toggleConversationListView
} from './conversationListPolicy.js'

const sessions = [
  { session_id: 'web-1', source: 'web', query: 'Web 对话' },
  { session_id: 'knowledge-1', source: 'knowledge_qa', query: '知识库对话' },
  { session_id: 'social-1', source: 'social', query: 'IM 对话' },
  {
    session_id: 'social-case',
    source: 'social',
    query: 'IM 案例',
    metadata: { is_case: true }
  },
  {
    session_id: 'web-case',
    source: 'web',
    query: 'Web 案例',
    metadata: { is_case: true }
  },
  {
    session_id: 'scheduled_task_daily_20260720_120000_abcd1234',
    source: 'web',
    query: '定时任务'
  }
]

test('recent and IM sidebar views keep Web and social conversations separate', () => {
  assert.deepEqual(
    filterSidebarConversations(sessions, CONVERSATION_LIST_VIEW.RECENT).map(row => row.session_id),
    ['web-1', 'knowledge-1', 'web-case']
  )
  assert.deepEqual(
    filterSidebarConversations(sessions, CONVERSATION_LIST_VIEW.IM).map(row => row.session_id),
    ['social-1', 'social-case']
  )
})

test('case library includes marked Web and social cases but never scheduled executions', () => {
  assert.deepEqual(
    filterSidebarConversations(sessions, CONVERSATION_LIST_VIEW.CASES).map(row => row.session_id),
    ['social-case', 'web-case']
  )
})

test('session history hides scheduled executions without hiding social conversations', () => {
  assert.deepEqual(
    filterConversationHistory(sessions).map(row => row.session_id),
    ['web-1', 'knowledge-1', 'social-1', 'social-case', 'web-case']
  )
})

test('session history totals match the filtered visible conversations', () => {
  assert.deepEqual(
    reconcileConversationHistoryStats(
      { total: 6, error_count: 1 },
      filterConversationHistory(sessions)
    ),
    { total: 5, error_count: 1 }
  )
})

test('conversation list icons switch mutually exclusively and toggle back to recent', () => {
  assert.equal(
    toggleConversationListView(CONVERSATION_LIST_VIEW.RECENT, CONVERSATION_LIST_VIEW.IM),
    CONVERSATION_LIST_VIEW.IM
  )
  assert.equal(
    toggleConversationListView(CONVERSATION_LIST_VIEW.IM, CONVERSATION_LIST_VIEW.CASES),
    CONVERSATION_LIST_VIEW.CASES
  )
  assert.equal(
    toggleConversationListView(CONVERSATION_LIST_VIEW.CASES, CONVERSATION_LIST_VIEW.CASES),
    CONVERSATION_LIST_VIEW.RECENT
  )
})

const knownModeIds = ['assistant', 'expert', 'query', 'knowledge', 'report', 'ops', 'ppt', 'board']

test('agent mode resolution prefers metadata then session id prefix then assistant', () => {
  assert.equal(resolveConversationAgentMode({ metadata: { mode: 'expert' } }), 'expert')
  assert.equal(resolveConversationAgentMode({ session_id: 'query_session_123' }), 'query')
  assert.equal(resolveConversationAgentMode({ session_id: 'no-prefix' }), 'assistant')
  assert.equal(resolveConversationAgentMode({}), 'assistant')
})

test('grouping keeps recency order and buckets unknown modes under other', () => {
  const sessions = [
    { session_id: 's1', metadata: { mode: 'expert' } },
    { session_id: 's2', metadata: { mode: 'assistant' } },
    { session_id: 's3', metadata: { mode: 'expert' } },
    { session_id: 's4', metadata: { mode: 'legacy_mode' } },
    { session_id: 's5' }
  ]
  const groups = groupSidebarConversationsByMode(sessions, knownModeIds)
  assert.deepEqual(groups.map(group => group.mode), ['expert', 'assistant', 'other'])
  assert.deepEqual(groups[0].sessions.map(row => row.session_id), ['s1', 's3'])
  assert.deepEqual(groups[1].sessions.map(row => row.session_id), ['s2', 's5'])
  assert.deepEqual(groups[2].sessions.map(row => row.session_id), ['s4'])
})

test('grouping handles empty lists', () => {
  assert.deepEqual(groupSidebarConversationsByMode([], knownModeIds), [])
})
