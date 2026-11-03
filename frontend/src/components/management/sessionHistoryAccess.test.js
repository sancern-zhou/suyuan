import test from 'node:test'
import assert from 'node:assert/strict'

import { historyRowLabels, preserveCatalogFields, sidebarOwnerBadge } from './sessionHistoryAccess.js'

test('catalog fields survive session history merges', () => {
  const merged = preserveCatalogFields(
    { session_id: 's1', source: 'knowledge_qa', owner_username: 'alice' },
    { session_id: 's1', query: 'hello' }
  )

  assert.equal(merged.source, 'knowledge_qa')
  assert.equal(merged.owner_username, 'alice')
})

test('administrator labels include source and owner', () => {
  assert.deepEqual(
    historyRowLabels(
      { source: 'web', owner_display_name: 'Alice', owner_username: 'alice' },
      true
    ),
    { source: 'Web', owner: 'Alice（alice）', readOnly: false }
  )
})

test('social conversations are labelled read-only without exposing owner to users', () => {
  assert.deepEqual(
    historyRowLabels(
      { source: 'social', owner_display_name: 'Alice', read_only_on_web: true },
      false
    ),
    { source: '微信', owner: '', readOnly: true }
  )
})

test('sidebar owner badge shows display name only for other users conversations', () => {
  assert.equal(
    sidebarOwnerBadge(
      { owner_user_id: 'u2', owner_display_name: '张三', owner_username: 'zhangsan' },
      'u1'
    ),
    '张三'
  )
  assert.equal(
    sidebarOwnerBadge(
      { owner_user_id: 'u1', owner_display_name: '张三', owner_username: 'zhangsan' },
      'u1'
    ),
    ''
  )
})

test('sidebar owner badge falls back to account and hides unowned sessions', () => {
  assert.equal(
    sidebarOwnerBadge({ owner_user_id: 'u2', owner_username: 'zhangsan' }, 'u1'),
    'zhangsan'
  )
  assert.equal(sidebarOwnerBadge({ query: '新对话' }, 'u1'), '')
  // 当前用户未知(如鉴权引导未完成)时不隐藏归属
  assert.equal(sidebarOwnerBadge({ owner_user_id: 'u2', owner_username: 'zhangsan' }, ''), 'zhangsan')
})
