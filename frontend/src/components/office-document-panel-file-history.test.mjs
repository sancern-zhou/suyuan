import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const componentPath = resolve(__dirname, './OfficeDocumentPanel.vue')
const source = readFileSync(componentPath, 'utf8')

assert.match(
  source,
  /文件历史/,
  'OfficeDocumentPanel should expose a file history section'
)

assert.doesNotMatch(
  source,
  /编辑历史|editHistory|showHistory|toggleHistory/,
  'OfficeDocumentPanel should remove the old edit history implementation'
)

assert.match(
  source,
  /v-for="doc in activeDocumentList"/,
  'OfficeDocumentPanel should render only the selected active preview document'
)

assert.match(
  source,
  /function selectDocument\(doc\)[\s\S]*activeDocumentId\.value = key/,
  'OfficeDocumentPanel should allow users to restore a previous file preview'
)

assert.match(
  source,
  /reactStore\.officeDocumentHistory/,
  'OfficeDocumentPanel should source file history from session store so tab remounts do not drop older files'
)
