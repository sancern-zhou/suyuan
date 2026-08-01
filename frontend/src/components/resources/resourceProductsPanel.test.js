import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = await readFile(new URL('./ResourceProductsPanel.vue', import.meta.url), 'utf8')

test('file products panel selects opaque resources without emitting preview payloads', () => {
  assert.match(source, /useSessionResourceStore/)
  assert.match(source, /selectGroup/)
  assert.match(source, /selectResource/)
  assert.match(source, /open-resource-tab/)
  assert.doesNotMatch(source, /file_path|pdf_id|html_id|\/api\/file\//)
  assert.doesNotMatch(source, /emit\([^\n]+preview/)
})
