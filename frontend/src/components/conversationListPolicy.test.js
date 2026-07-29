import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CONVERSATION_LIST_VIEW,
  filterConversationHistory,
  filterSidebarConversations,
  reconcileConversationHistoryStats,
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
