import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'

const __dirname = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(__dirname, './QueryDashboardWorkspace.vue'), 'utf8')
const mapSource = readFileSync(resolve(__dirname, './GuangdongOverviewMap.vue'), 'utf8')

test('query dashboard layout keeps chat on the right and controls at bottom left', () => {
  assert.doesNotMatch(source, /<DashboardFocusPanel\b/, 'query focus panel should not be rendered')
  assert.doesNotMatch(source, /class="source-button"/, 'data source button should not be rendered')
  assert.match(source, /\.dashboard-side\s*\{[\s\S]*?left:\s*16px;[\s\S]*?bottom:\s*16px;/)
  assert.match(source, /\.chat-overlay\s*\{[\s\S]*?top:\s*16px;[\s\S]*?right:\s*18px;[\s\S]*?width:\s*min\(380px, calc\(100% - 36px\)\);/)
  assert.doesNotMatch(source, /\.chat-overlay\s*\{[\s\S]*?left:\s*18px;[\s\S]*?bottom:\s*16px;/)
  assert.doesNotMatch(mapSource, /关注范围|关注城市|关注站点|focusLabel/)
})
