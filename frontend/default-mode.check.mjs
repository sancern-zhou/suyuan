import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const read = (relativePath) => readFileSync(join(__dirname, relativePath), 'utf8')

const storeSource = read('src/stores/reactStore.js')
const viewSource = read('src/views/ReactAnalysisView.vue')

assert.match(
  storeSource,
  /localStorage\.getItem\('current-mode'\)\s*\|\|\s*'assistant'/,
  'react store should default current-mode to assistant'
)

assert.doesNotMatch(
  viewSource,
  /store\.currentMode\s*!==\s*'query'[\s\S]*?store\.switchMode\('query'\)/,
  'ReactAnalysisView should not force query mode on mount'
)

console.log('Default mode check passed')
