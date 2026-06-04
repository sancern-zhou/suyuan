import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(__dirname, './useSessionRecovery.js'), 'utf8')

assert.match(
  source,
  /result\.visuals/,
  'Session recovery should extract top-level result.visuals'
)

assert.match(
  source,
  /result\.tool_results/,
  'Session recovery should extract visuals from nested tool_results'
)

assert.doesNotMatch(
  source,
  /initialMessageLimit\s*=\s*30/,
  'Session recovery should not default to a 30-message first page that can split the latest conversation turn'
)

console.log('useSessionRecovery tests passed')
