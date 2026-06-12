import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const storePath = resolve(__dirname, './reactStore.js')
const sessionPath = resolve(__dirname, '../composables/reactAnalysis/useSessionManagement.js')
const storeSource = readFileSync(storePath, 'utf8')
const sessionSource = readFileSync(sessionPath, 'utf8')

assert.match(
  storeSource,
  /officeDocumentHistory:\s*\[\]/,
  'reactStore session state should keep full office document history'
)

assert.match(
  storeSource,
  /officeDocumentHistory\(\)\s*\{\s*return this\.currentState\?\.officeDocumentHistory \|\| \[\]/,
  'reactStore should expose officeDocumentHistory to remounted panels'
)

assert.match(
  storeSource,
  /recordOfficeDocument\(doc,\s*targetState = this\.currentState\)/,
  'reactStore should have one path for recording office document previews'
)

assert.match(
  storeSource,
  /targetState\.officeDocumentHistory\.push\(normalizedDoc\)/,
  'recordOfficeDocument should append new preview files instead of replacing history'
)

assert.doesNotMatch(
  storeSource,
  /targetState\.lastOfficeDocument = \{\s*(?:pdf_preview|html_preview|markdown_preview)/,
  'SSE handlers should not bypass officeDocumentHistory by writing lastOfficeDocument directly'
)

assert.match(
  storeSource,
  /case 'complete':[\s\S]*data\?\.office_documents[\s\S]*recordOfficeDocument\(/,
  'complete events should merge office_documents into history so missed live preview events still refresh the file panel'
)

assert.match(
  storeSource,
  /targetState\.officeDocumentHistory\.splice\(existingIndex,\s*1\)[\s\S]*targetState\.officeDocumentHistory\.push\(updatedDoc\)/,
  'updated office documents should move to the end so the latest preview becomes active'
)

assert.match(
  storeSource,
  /setOfficeDocumentHistory\(documents\)[\s\S]*\.slice\(\)[\s\S]*\.sort\(\(a,\s*b\)[\s\S]*new Date\(a\?\.timestamp \|\| 0\)[\s\S]*new Date\(b\?\.timestamp \|\| 0\)[\s\S]*\.forEach\(doc => this\.recordOfficeDocument\(doc,\s*this\.currentState\)\)/,
  'session restore should sort office documents oldest-first so the newest preview remains active'
)

assert.match(
  storeSource,
  /related_files:\s*doc\.related_files/,
  'office document records should preserve related artifact download files'
)

assert.match(
  storeSource,
  /artifacts:\s*doc\.artifacts/,
  'office document records should preserve artifact download metadata'
)

assert.match(
  storeSource,
  /doc\.svg_preview\?\.svg_url[\s\S]*doc\.svg_preview\?\.svg_path/,
  'diagram documents should use svg_preview as a stable office document identity'
)

assert.match(
  sessionSource,
  /setOfficeDocumentHistory\(officeDocs\)/,
  'session restore should hydrate the full document history, not only the latest document'
)
