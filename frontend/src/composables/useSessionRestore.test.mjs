import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(__dirname, './useSessionRestore.js'), 'utf8')

assert.match(
  source,
  /import\s*\{\s*restoreSession\s+as\s+restoreSessionApi/,
  'useSessionRestore should alias the API restoreSession import so the local restoreSession function does not recurse'
)

assert.match(
  source,
  /const\s+response\s*=\s*await\s+restoreSessionApi\(/,
  'useSessionRestore should call the aliased API restoreSession function'
)

console.log('useSessionRestore recursion guard passed')
