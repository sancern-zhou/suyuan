import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(__dirname, './useSessionManagement.js'), 'utf8')

assert.doesNotMatch(
  source,
  /else\s+if\s*\(resultData\.markdown_preview\)[\s\S]*?else\s+if\s*\(resultData\.html_preview\)/,
  'Session recovery must not drop html_preview when markdown_preview is also present'
)

assert.match(
  source,
  /html_preview:\s*resultData\.html_preview/,
  'Recovered office documents should preserve html_preview for report iframe previews'
)

assert.doesNotMatch(
  source,
  /doRestoreSession\(sessionId,\s*\{\s*messageLimit:\s*30/,
  'Session restore should not use a 30-message first page that can split the latest conversation turn'
)

console.log('useSessionManagement recovery tests passed')
