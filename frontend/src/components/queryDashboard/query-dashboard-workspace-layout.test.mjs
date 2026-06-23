import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'

const __dirname = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(__dirname, './QueryDashboardWorkspace.vue'), 'utf8')
const mapSource = readFileSync(resolve(__dirname, './GuangdongOverviewMap.vue'), 'utf8')

const cssBlock = (selector) => {
  const escapedSelector = selector.replaceAll('.', '\\.')
  const match = source.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`))
  assert.ok(match, `${selector} style block should exist`)
  return match[1]
}

test('query dashboard layout keeps chat on the right and controls at bottom left', () => {
  const chatOverlayBlock = cssBlock('.chat-overlay')
  const modeSelectorBlock = cssBlock('.dashboard-mode-selector')
  const modeSelectorOverrideBlock = cssBlock('.dashboard-mode-selector.agent-mode-selector')

  assert.doesNotMatch(source, /<DashboardFocusPanel\b/, 'query focus panel should not be rendered')
  assert.doesNotMatch(source, /class="source-button"/, 'data source button should not be rendered')
  assert.match(source, /<AgentModeSelector\b[\s\S]*?class="dashboard-mode-selector"/, 'mode selector should be outside the chat overlay')
  assert.match(source, /:hide-welcome="true"/, 'query dashboard should hide the generic welcome copy')
  assert.match(source, /:show-agent-mode-selector="false"/, 'query dashboard should hide the mode selector inside InputBox')
  assert.match(source, /\.dashboard-side\s*\{[\s\S]*?left:\s*16px;[\s\S]*?bottom:\s*16px;/)
  assert.match(chatOverlayBlock, /top:\s*16px;/)
  assert.match(chatOverlayBlock, /right:\s*18px;/)
  assert.match(chatOverlayBlock, /width:\s*min\(480px, calc\(100% - 36px\)\);/)
  assert.match(modeSelectorBlock, /right:\s*18px;/)
  assert.match(modeSelectorBlock, /bottom:\s*16px;/)
  assert.match(modeSelectorBlock, /width:\s*min\(480px, calc\(100% - 36px\)\);/)
  assert.match(modeSelectorBlock, /justify-content:\s*space-between;/)
  assert.match(modeSelectorBlock, /align-items:\s*center;/)
  assert.match(modeSelectorBlock, /flex-wrap:\s*nowrap;/)
  assert.match(modeSelectorOverrideBlock, /justify-content:\s*space-between;/)
  assert.match(modeSelectorOverrideBlock, /flex-wrap:\s*nowrap;/)
  assert.doesNotMatch(source, /\.chat-overlay\s*\{[\s\S]*?left:\s*18px;[\s\S]*?bottom:\s*16px;/)
  assert.doesNotMatch(mapSource, /关注范围|关注城市|关注站点|focusLabel/)
})
