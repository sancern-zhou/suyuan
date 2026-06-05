import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const componentPath = resolve(__dirname, './OfficeDocumentPanel.vue')
const source = readFileSync(componentPath, 'utf8')

assert.match(
  source,
  /downloadOriginalFile/,
  'OfficeDocumentPanel should provide a generic original-file download action for presented artifacts'
)

assert.match(
  source,
  /doc\.html_url/,
  'OfficeDocumentPanel should preview any presented artifact with an html_url'
)

assert.match(
  source,
  /\['html', 'image'\]/,
  'OfficeDocumentPanel should classify present_artifact HTML and image files for preview'
)

assert.match(
  source,
  /generator:\s*doc\.generator/,
  'OfficeDocumentPanel should retain the generator so present_artifact can alter UI behavior'
)
