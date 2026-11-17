import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CONVERSATION_LIST_LAYOUT,
  CONVERSATION_LIST_VIEW,
  compareConversationRecency,
  conversationRecency,
  filterConversationHistory,
  filterSidebarConversations,
  groupSidebarConversationsByMode,
  localConversationFallback,
  parseConversationTimestamp,
  parseMessageTimestamp,
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

test('recency is driven by persisted updated_at, not client message timestamps', () => {
  const older = { session_id: 'a', updated_at: '2026-11-17T08:00:00' }
  const newer = { session_id: 'b', updated_at: '2026-11-17T09:00:00' }
  assert.ok(conversationRecency(newer) > conversationRecency(older))

  const sorted = [older, newer].sort(compareConversationRecency)
  assert.deepEqual(sorted.map(row => row.session_id), ['b', 'a'])
})

test('running sessions stay pinned above completed ones regardless of recency', () => {
  const running = { session_id: 'running', updated_at: '2026-11-17T08:00:00', is_running: true }
  const recent = { session_id: 'recent', updated_at: '2026-11-17T09:00:00' }
  const sorted = [recent, running].sort(compareConversationRecency)
  assert.deepEqual(sorted.map(row => row.session_id), ['running', 'recent'])
})

test('missing or invalid updated_at sorts last instead of pretending to be now', () => {
  const stale = { session_id: 'stale' }
  const invalid = { session_id: 'invalid', updated_at: 'not-a-date' }
  const dated = { session_id: 'dated', updated_at: '2026-11-17T09:00:00' }

  assert.equal(conversationRecency(stale), 0)
  assert.equal(conversationRecency(invalid), 0)
  assert.deepEqual(
    [stale, invalid, dated].sort(compareConversationRecency).map(row => row.session_id),
    ['dated', 'stale', 'invalid']
  )
})

test('naive server timestamps are read as UTC, not browser local time', () => {
  // 服务端 updated_at 是无时区的 UTC；消息 timestamp 来自 UTC ISO 字符串。
  // 两者必须落在同一时间轴上，不能因为浏览器时区产生 8 小时偏差。
  const serverUtc = '2026-11-17T08:00:00'
  const clientUtc = '2026-11-17T08:00:00.000Z'
  assert.equal(parseConversationTimestamp(serverUtc), parseConversationTimestamp(clientUtc))
  assert.equal(
    parseConversationTimestamp(serverUtc),
    Date.parse('2026-11-17T08:00:00Z')
  )
  assert.equal(
    parseConversationTimestamp('2026-11-17T16:00:00+08:00'),
    Date.parse('2026-11-17T08:00:00Z')
  )
})

test('local message fallback reads naive CST and matches the server UTC axis', () => {
  // session_messages.timestamp 存的是无时区本地时间（CST），与 UTC 的
  // updated_at 相差 8 小时，必须按 +08:00 解析后才能比较。
  assert.equal(
    parseMessageTimestamp('2026-11-17T16:53:14'),
    Date.parse('2026-11-17T08:53:14Z')
  )
  // 运行期新消息带 Z，按其自身 UTC 解析。
  assert.equal(
    parseMessageTimestamp('2026-11-17T08:53:14.000Z'),
    Date.parse('2026-11-17T08:53:14Z')
  )
  assert.equal(localConversationFallback(null), null)
  assert.equal(localConversationFallback(''), null)
  assert.equal(
    localConversationFallback('2026-11-17T16:53:14'),
    '2026-11-17T08:53:14.000Z'
  )

  // 同一个真实时刻的服务端时间与本地消息兜底必须排成平手而不是差 8 小时。
  const server = { session_id: 'server', updated_at: '2026-11-17T08:53:14' }
  const local = { session_id: 'local', updated_at: localConversationFallback('2026-11-17T16:53:14') }
  assert.equal(conversationRecency(server), conversationRecency(local))
})
