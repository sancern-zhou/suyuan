import { readFileSync } from 'node:fs'
import { strict as assert } from 'node:assert'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

const sessionApi = read('./src/api/session.js')
assert.match(sessionApi, /limit\s*=\s*200/, 'listSessions should default to 200')

const sessionRoutes = read('../backend/app/api/session_routes.py')
assert.match(sessionRoutes, /SESSION_LIST_DEFAULT_LIMIT\s*=\s*200/, 'backend sessions route should default to 200')

const sessionManagement = read('./src/composables/reactAnalysis/useSessionManagement.js')
assert.match(sessionManagement, /listSessions\(\{\s*limit:\s*200\s*\}\)/, 'session history refresh should request 200 sessions')
assert.match(sessionManagement, /const\s+deleteSessions\s*=\s*async\s*\(/, 'session management should expose batch delete')
assert.match(sessionManagement, /deleteSessions,/, 'deleteSessions should be returned from useSessionManagement')

const historyPanel = read('./src/components/management/SessionHistoryPanel.vue')
assert.match(historyPanel, /selectedSessionIds/, 'history panel should track selected sessions')
assert.match(historyPanel, /delete-sessions/, 'history panel should emit delete-sessions')
assert.match(historyPanel, /type="checkbox"/, 'history panel should render selection checkboxes')

const mainLayout = read('./src/components/reactAnalysis/MainLayout.vue')
assert.match(mainLayout, /@delete-sessions="\$emit\('delete-sessions', \$event\)"/, 'main layout should forward delete-sessions')
assert.match(mainLayout, /'delete-sessions'/, 'main layout should declare delete-sessions emit')

const view = read('./src/views/ReactAnalysisView.vue')
assert.match(view, /@delete-sessions="deleteSessions"/, 'main view should wire delete-sessions')

const refactoredView = read('./src/views/ReactAnalysisViewRefactored.vue')
assert.match(refactoredView, /@delete-sessions="deleteSessions"/, 'refactored view should wire delete-sessions')

const sidebar = read('./src/components/AssistantSidebar.vue')
assert.match(sidebar, /SESSION_FETCH_LIMIT\s*=\s*200/, 'assistant sidebar should fetch 200 sessions')
