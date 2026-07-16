import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveRestoredAgentMode } from './restoreModePolicy.js'

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

test('mode-prefixed ids remain a fallback for legacy sessions', () => {
  assert.equal(resolveRestoredAgentMode({}, 'chart_session_123_abc', 'assistant'), 'chart')
})

test('unsupported metadata falls back to the current supported mode', () => {
  assert.equal(resolveRestoredAgentMode({
    metadata: { mode: 'knowledge_qa' }
  }, 'opaque-history-id', 'expert'), 'expert')
})
