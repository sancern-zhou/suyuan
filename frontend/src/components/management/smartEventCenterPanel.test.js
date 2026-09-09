import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const source = fs.readFileSync(
  path.join(import.meta.dirname, 'SmartEventCenterPanel.vue'),
  'utf8'
)

test('smart event center renders a fixed list and detail surface', () => {
  assert.match(source, /aria-label="智能事件列表"/)
  assert.match(source, /aria-label="智能事件详情"/)
  assert.match(source, /ai_judgment/)
  assert.match(source, /final_response/)
})

test('smart event detail can open the corresponding scheduled task workspace', () => {
  assert.match(source, /listJiangsuSmartEventTasks/)
  assert.match(source, /\$emit\('open-task', task\)/)
  assert.match(source, /task\.task_id/)
})

test('smart event workspace handles Agent focus, comparison, history, and task commands', () => {
  assert.match(source, /command\.type === 'focus_evidence'/)
  assert.match(source, /command\.type === 'compare_events'/)
  assert.match(source, /command\.type === 'show_operation_history'/)
  assert.match(source, /command\.type === 'open_task'/)
  assert.match(source, /workspaceMode === 'compare'/)
  assert.match(source, /workspaceMode === 'history'/)
})

test('fixed event detail exposes confirmation and archive controls', () => {
  assert.match(source, /submitJiangsuSmartEventJudgment/)
  assert.match(source, /archiveJiangsuSmartEvent/)
  assert.match(source, /保存并确认/)
  assert.match(source, /归档事件/)
})
