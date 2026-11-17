import assert from 'node:assert/strict'
import test from 'node:test'

import { fatalErrorDisplayText, isSilentErrorEvent } from './reactStoreErrorEvents.js'

test('瞬时故障事件带 silent 标记时不渲染气泡', () => {
  assert.equal(isSilentErrorEvent({ silent: true, error: "Server error '504 Gateway Time-out'" }), true)
  assert.equal(isSilentErrorEvent({ error: 'bad request' }), false)
  assert.equal(isSilentErrorEvent(null), false)
})

test('致命错误优先展示后端给的友好文案', () => {
  assert.equal(
    fatalErrorDisplayText({ user_message: '模型服务暂时不可用，请稍后重试。', error: "Server error '504'" }),
    '模型服务暂时不可用，请稍后重试。'
  )
  assert.equal(fatalErrorDisplayText({ error: 'boom' }), 'boom')
  assert.equal(fatalErrorDisplayText({}), '致命错误')
})
