import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const readSource = relativePath => readFile(new URL(relativePath, import.meta.url), 'utf8')

test('sidebar exposes the agent platform as a primary action', async () => {
  const source = await readSource('../AssistantSidebar.vue')

  assert.match(source, /agent-platform/)
  assert.match(source, /智能体平台/)
})

test('main layout switches between agent platform and chat workspace', async () => {
  const source = await readSource('../reactAnalysis/MainLayout.vue')

  assert.match(source, /workspace === 'platform'/)
  assert.match(source, /<AgentPlatform/)
  assert.match(source, /<AgentWorkspaceHeader/)
  assert.match(source, /select-agent/)
})

test('analysis view defaults to the platform and opens chat through explicit flows', async () => {
  const source = await readSource('../../views/ReactAnalysisView.vue')

  assert.match(source, /const workspace = ref\('platform'\)/)
  assert.match(source, /resolveAgentSelection/)
  assert.match(source, /workspace\.value = 'chat'/)
  assert.match(source, /workspace\.value = 'platform'/)
  assert.match(source, /route\.params\.id/)
})
