import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const source = readFileSync(new URL('./InputBox.vue', import.meta.url), 'utf8')


test('defines the board sync status consumed by send guards', () => {
  assert.match(
    source,
    /const\s+boardSyncStatus\s*=\s*computed\([^]*?syncStatus/,
    'InputBox must define boardSyncStatus before actionButtonDisabled and handleSend read it'
  )
  assert.match(source, /boardSyncStatus\.value\s*===\s*['"]syncing['"]/)
})
