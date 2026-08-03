import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('visualization gallery scrolls inside a dedicated panel host', async () => {
  const panelSource = await readFile(
    new URL('../reactAnalysis/RightPanelContainer.vue', import.meta.url),
    'utf8'
  )
  const gallerySource = await readFile(new URL('./VisualizationGallery.vue', import.meta.url), 'utf8')
  const galleryUsage = panelSource.match(/<VisualizationGallery[\s\S]*?\/>/)?.[0] || ''

  assert.match(panelSource, /class="panel-content visualization-panel-host"/)
  assert.doesNotMatch(galleryUsage, /class="panel-content"/)
  assert.match(gallerySource, /overflow-y:\s*auto/)
  assert.match(gallerySource, /overflow-x:\s*hidden/)
})
