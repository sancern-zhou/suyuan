import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveRestoredAgentMode, resolveRestoredNativeMode } from './restoreModePolicy.js'

test('opaque historical session ids use authoritative metadata mode', () => {
  assert.equal(resolveRestoredAgentMode({
    metadata: { mode: 'query' }
  }, 'opaque-history-id', 'assistant'), 'query')
})

test('top-level persisted mode takes priority when available', () => {
  assert.equal(resolveRestoredAgentMode({
    mode: 'report',
    metadata: { mode: 'assistant' }
  }, 'opaque-history-id', 'expert'), 'report')
})

test('assistant Web history restores the existing assistant entry without losing metadata priority', () => {
  assert.equal(resolveRestoredAgentMode({ mode: 'assistant' }, 'opaque-id', 'query'), 'assistant')
  assert.equal(resolveRestoredAgentMode({ metadata: { mode: 'assistant' } }, 'opaque-id', 'expert'), 'assistant')
})

test('mode-prefixed ids remain a fallback for legacy sessions', () => {
  assert.equal(resolveRestoredAgentMode({}, 'chart_session_123_abc', 'assistant'), 'assistant')
  assert.equal(resolveRestoredAgentMode({}, 'board_session_123_abc', 'assistant'), 'board')
  assert.equal(resolveRestoredAgentMode({}, 'ppt_session_123_abc', 'assistant'), 'ppt')
  assert.equal(resolveRestoredAgentMode({}, 'knowledge_session_123_abc', 'assistant'), 'knowledge')
})

test('unsupported metadata falls back to the current supported mode', () => {
  assert.equal(resolveRestoredAgentMode({
    metadata: { mode: 'knowledge_qa' }
  }, 'opaque-history-id', 'expert'), 'expert')
})

test('native custom mode is surfaced raw even though it is not a UI mode', () => {
  assert.equal(resolveRestoredNativeMode({
    mode: 'custom',
    metadata: { mode: 'custom' }
  }), 'custom')
  assert.equal(resolveRestoredNativeMode({
    metadata: { mode: 'custom' }
  }), 'custom')
  assert.equal(resolveRestoredNativeMode({ mode: 'assistant' }), 'assistant')
  assert.equal(resolveRestoredNativeMode({}), null)
  // UI 视图模式仍走模式表过滤；custom 会话恢复后视图停在当前模式
  assert.equal(resolveRestoredAgentMode({
    mode: 'custom',
    metadata: { mode: 'custom' }
  }, 'scheduled_task_x_20261109_100000_abc', 'assistant'), 'assistant')
})
