import assert from 'node:assert/strict'
import test from 'node:test'
import { normalizeRestoredContent, normalizeRestoredMessages } from './sessionContent.js'

test('decodes a JSON-serialized Chinese history message', () => {
  assert.equal(
    normalizeRestoredContent('"## \\u5173\\u4e8e\\u9065\\u611f\\n\\n\\u6570\\u636e"'),
    '## 关于遥感\n\n数据'
  )
})

test('decodes unquoted Unicode escapes from legacy history content', () => {
  assert.equal(
    normalizeRestoredContent('<p>\\u5173\\u4e8e\\u9065\\u611f\\u6570\\u636e</p>'),
    '<p>关于遥感数据</p>'
  )
})

test('leaves normal and non-string history content unchanged', () => {
  assert.equal(normalizeRestoredContent('## 关于遥感数据'), '## 关于遥感数据')
  assert.equal(normalizeRestoredContent('{"title":"关于遥感数据"}'), '{"title":"关于遥感数据"}')
  assert.deepEqual(normalizeRestoredMessages([{ content: ['text'] }]), [{ content: ['text'] }])
})
