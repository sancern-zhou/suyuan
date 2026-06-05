import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const sidebarSource = readFileSync(resolve(__dirname, './AssistantSidebar.vue'), 'utf8')
const panelSource = readFileSync(resolve(__dirname, './management/SessionHistoryPanel.vue'), 'utf8')
const apiSource = readFileSync(resolve(__dirname, '../api/session.js'), 'utf8')
const managementSource = readFileSync(resolve(__dirname, '../composables/reactAnalysis/useSessionManagement.js'), 'utf8')

assert.match(
  apiSource,
  /export\s+async\s+function\s+markSessionCase\s*\(/,
  'Session API should expose markSessionCase'
)

assert.match(
  apiSource,
  /export\s+async\s+function\s+unmarkSessionCase\s*\(/,
  'Session API should expose unmarkSessionCase'
)

assert.match(
  sidebarSource,
  /showCaseLibrary/,
  'Assistant sidebar should maintain case-library toggle state'
)

assert.match(
  sidebarSource,
  /caseLibrarySessions/,
  'Assistant sidebar should derive case-library sessions from recent sessions'
)

assert.doesNotMatch(
  sidebarSource,
  /@click="refreshRecentSessions"[\s\S]*title="刷新"/,
  'Assistant sidebar should replace the manual refresh icon with case-library access'
)

assert.match(
  panelSource,
  /toggle-session-case/,
  'Session history panel should emit toggle-session-case from row action'
)

assert.match(
  panelSource,
  /isSessionCase/,
  'Session history panel should render case mark state'
)

assert.match(
  managementSource,
  /handleToggleSessionCase/,
  'Session management composable should handle case toggles'
)

assert.match(
  managementSource,
  /applySessionCaseState\(session\.session_id,\s*!isCase/,
  'Case toggle should optimistically update local session history before waiting for a full refresh'
)

assert.match(
  managementSource,
  /applySessionCaseState\(session\.session_id,\s*isCase,\s*previousMetadata\)/,
  'Case toggle should roll back optimistic metadata when the API call fails'
)

console.log('case library source tests passed')
