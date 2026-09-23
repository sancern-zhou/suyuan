import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('interactive chart cards expose a download button that renders the canvas', async () => {
  const card = await readFile(new URL('./VisualizationCard.vue', import.meta.url), 'utf8')
  assert.match(card, /v-if="downloadTarget\?\.download_url \|\| isChart"/)
  assert.match(card, /rendererKey\(props\.resource\) === 'chart'/)
  assert.match(card, /ref="rendererRef"/)
  assert.match(card, /rendererRef\.value\?\.getChartImage\?\.\(\)/)
  assert.match(card, /link\.download = `\$\{chartFileName\.value\}\.png`/)

  const renderer = await readFile(
    new URL('./renderers/ChartResourceRenderer.vue', import.meta.url), 'utf8'
  )
  assert.match(renderer, /ref="panelRef"/)
  assert.match(renderer, /defineExpose\(\{ getChartImage \}\)/)
  assert.match(renderer, /panelRef\.value\.getChartImage/)
})
