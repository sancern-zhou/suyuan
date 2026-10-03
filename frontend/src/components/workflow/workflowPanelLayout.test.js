import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readComponent = name => readFile(new URL(name, import.meta.url), 'utf8')

test('workflow uses an ordered stage list instead of a connection diagram', async () => {
  const source = await readComponent('./WorkflowPanel.vue')

  assert.match(source, /class="workflow-stage-list"/)
  assert.match(source, /class="workflow-node-row"/)
  assert.match(source, /并行 \$\{stage\.length\} 个节点/)
  assert.match(source, /dependencyLabel\(node\)/)
  assert.doesNotMatch(source, /dag-edges|dag-canvas|<svg/)
  assert.doesNotMatch(source, /summary-grid|nodeStats/)
})

test('clicking a node opens a dedicated child agent conversation review', async () => {
  const source = await readComponent('./WorkflowPanel.vue')

  assert.match(source, /class="subagent-review"/)
  assert.match(source, /子 Agent 对话审查/)
  assert.match(source, /nodeHistory\.value\?\.conversation/)
  assert.match(source, /refreshNodeHistory/)
  assert.match(source, /closeNodeInspection/)
  assert.match(source, /执行过程/)
})

test('workflow panel owns a vertical scroll container', async () => {
  const workflowSource = await readComponent('./WorkflowPanel.vue')
  const hostSource = await readComponent('../reactAnalysis/RightPanelContainer.vue')

  assert.match(workflowSource, /\.workflow-panel\s*\{[^}]*height:\s*100%[^}]*overflow:\s*auto/)
  assert.equal((hostSource.match(/class="panel-content workflow-panel-host"/g) || []).length, 2)
  assert.match(hostSource, /\.panel-content\.workflow-panel-host\s*\{[^}]*overflow-y:\s*auto/)
  assert.match(hostSource, /\.viz-wrapper\.workflow-active\s*\{[^}]*min-width:/)
})
