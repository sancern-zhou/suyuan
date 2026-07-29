import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

test('G6 canvas owns rendering lifecycle and emits graph selection events', () => {
  const source = fs.readFileSync(new URL('./KnowledgeGraphCanvas.vue', import.meta.url), 'utf8')
  assert.match(source, /import \{ Graph \} from '@antv\/g6'/)
  assert.match(source, /defineProps/)
  assert.match(source, /node-click/)
  assert.match(source, /relation-click/)
  assert.match(source, /onUnmounted/)
  assert.match(source, /graph\.destroy/)
  assert.match(source, /defineExpose/)
})

test('toolbar exposes search filters labels layout fullscreen history and refresh', () => {
  const source = fs.readFileSync(new URL('./KnowledgeGraphToolbar.vue', import.meta.url), 'utf8')
  for (const event of ['search', 'entity-filter', 'relation-filter', 'labels', 'fit', 'layout', 'fullscreen', 'history', 'refresh']) {
    assert.match(source, new RegExp(event))
  }
})
