import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const storePath = resolve(__dirname, './reactStore.js')
const source = readFileSync(storePath, 'utf8')

assert.match(
  source,
  /buildPresentedImageVisual/,
  'reactStore should convert present_artifact image payloads into visualization records'
)

assert.match(
  source,
  /type:\s*'image'/,
  'present_artifact image visuals should use VisualizationPanel image type'
)

assert.match(
  source,
  /image_url:\s*imageUrl/,
  'present_artifact image visuals should expose image_url for ImagePanel'
)

assert.match(
  source,
  /!isPresentedImage\s*&&\s*\(resultData\.pdf_preview \|\| resultData\.markdown_preview \|\| resultData\.html_preview\)/,
  'present_artifact image results should not be routed into lastOfficeDocument'
)

assert.match(
  source,
  /this\.recordVisualization\(visual,\s*targetState\)/,
  'present_artifact image tool_result events should open the visualization path'
)
