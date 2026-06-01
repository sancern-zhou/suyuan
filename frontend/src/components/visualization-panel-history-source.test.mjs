import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const componentPath = resolve(__dirname, './VisualizationPanel.vue')
const source = readFileSync(componentPath, 'utf8')

assert.match(
  source,
  /props\.content\?\.visuals/,
  'VisualizationPanel should render lazy-loaded visuals passed via content.visuals'
)

assert.match(
  source,
  /visualizationHistory/,
  'VisualizationPanel should render lazy-loaded visuals from store.currentState.visualizationHistory'
)

