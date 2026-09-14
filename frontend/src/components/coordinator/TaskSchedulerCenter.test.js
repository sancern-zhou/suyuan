import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('all todo categories use submitted generic reviews and the shared detail panel', async () => {
  const source = await readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')
  assert.match(source, /listTaskReviews\(\)/)
  assert.match(source, /TaskReviewPanel :review-id="selectedReviewId"/)
  // 人工确认归档弹窗同样使用紧凑模式，避免信息过载。
  assert.match(source, /TaskReviewPanel :review-id="selectedReviewId" compact/)
  assert.match(source, /task\.category/)
  assert.match(source, /eventTasks/)
  assert.doesNotMatch(source, /fetchRecentExecutions|listJiangsuSmartEventTasks|executionToAttentionItem|smartEventTasks/)
})

test('todo cards navigate to the review conversation and keep archive as a secondary action', async () => {
  const source = await readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')
  assert.match(source, /emit\('select-review', task\)/)
  assert.match(source, /'select-task', 'select-review'/)
  assert.match(source, /task-action-secondary" @click="selectedReviewId = task\.review_id"/)
  const view = await readFile(new URL('../../views/ReactAnalysisView.vue', import.meta.url), 'utf8')
  assert.match(view, /@select-review="handleTodoReviewOpen"/)
  assert.match(view, /suppressSmartEventCommandOpen/)
  const layout = await readFile(new URL('../reactAnalysis/MainLayout.vue', import.meta.url), 'utf8')
  assert.match(layout, /@select-review="\$emit\('select-review', \$event\)"/)
})
