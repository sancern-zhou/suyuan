import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('all todo categories use submitted generic reviews and the shared detail panel', async () => {
  const source = await readFile(new URL('./TaskSchedulerCenter.vue', import.meta.url), 'utf8')
  assert.match(source, /listTaskReviews\(\)/)
  assert.match(source, /TaskReviewPanel :review-id="selectedReviewId"/)
  assert.match(source, /task\.category/)
  assert.match(source, /eventTasks/)
  assert.doesNotMatch(source, /fetchRecentExecutions|listJiangsuSmartEventTasks|executionToAttentionItem|smartEventTasks/)
})
