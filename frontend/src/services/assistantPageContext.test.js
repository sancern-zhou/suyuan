import assert from 'node:assert/strict'
import test from 'node:test'
import { buildAssistantPageContext } from './assistantPageContext.js'

test('uses a route allowlist and excludes credentials and arbitrary query strings', () => {
  assert.deepEqual(buildAssistantPageContext({ name: 'knowledge-base', meta: { title: '知识库管理' }, query: { token: 'secret', filter: '<script>' } }), {
    route_name: 'knowledge-base', title: '知识库管理'
  })
  assert.deepEqual(buildAssistantPageContext({ name: 'session', params: { id: 'assistant_session_1' }, meta: {} }), {
    route_name: 'session', title: '会话工作区', session_id: 'assistant_session_1'
  })
})

test('does not expose public, dashboard or unknown routes', () => {
  assert.equal(buildAssistantPageContext({ name: 'login', meta: { public: true } }), null)
  assert.equal(buildAssistantPageContext({ name: 'bigscreen', meta: { allowDashboardToken: true } }), null)
  assert.equal(buildAssistantPageContext({ name: 'unknown', meta: {} }), null)
})
