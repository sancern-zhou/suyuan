import { test, expect } from 'playwright/test'

const base = {
  review_id: 'review_123', task_id: 't', task_name: '审核任务', execution_id: 'run', subject_id: '业务-1',
  category: '工单审核', title: '故障处理需确认', summary: '已核验设备记录', decision: 'approve', comment: '建议通过',
  status: 'pending_review', version: 1, checks: [{ name: '事实一致性', status: 'pass', basis: '记录一致', missing_evidence: [] }],
  review_basis: ['SOP-01'], data_impact: [], evidence: [], actions: ['复核后归档'], sections: [],
}

test('generic review renders and persists human decision without a business renderer', async ({ page }) => {
  let record = structuredClone(base)
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/task-reviews/**', async route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON()
      expect(body.version).toBe(1)
      expect(body.comment).toBe('核验完成')
      record = { ...record, status: 'archived', version: 2, human_decision: { ...body, actor: { username: '审核员' }, occurred_at: '2026-09-10' } }
    }
    await route.fulfill({ json: { review: record } })
  })
  await page.route('**/__task_review_test__', route => route.fulfill({ contentType: 'text/html', body: `<div id="app" style="height:900px"></div><script type="module" src="/e2e/taskReviewHarness.js"></script>` }))
  await page.goto('/__task_review_test__')
  await expect(page.getByRole('heading', { name: '故障处理需确认' })).toBeVisible()
  await page.getByLabel('审核意见', { exact: true }).fill('核验完成')
  await page.getByRole('button', { name: '确认归档' }).click()
  await expect(page.getByRole('heading', { name: '人工处理记录' })).toBeVisible()
  await expect(page.getByRole('button', { name: '确认归档' })).toHaveCount(0)
  expect(errors).toEqual([])
})

test('scheduler classifies generic todos, opens shared review and removes confirmed items', async ({ page }) => {
  const records = [structuredClone(base), { ...structuredClone(base), review_id: 'review_456', category: '智能事件', title: '站点告警需确认' }]
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/scheduled-tasks')) return route.fulfill({ json: [{ task: { task_id: 'scheduled', name: '定时巡检', trigger_type: 'schedule', enabled: true } }, { task: { task_id: 'event', name: '告警研判', trigger_type: 'event', enabled: true } }] })
    if (url.pathname.endsWith('/task-reviews')) return route.fulfill({ json: { reviews: records.filter(record => record.status === 'pending_review'), total: records.filter(record => record.status === 'pending_review').length } })
    const record = records.find(record => url.pathname.includes(record.review_id))
    if (record) {
      if (route.request().method() === 'POST') Object.assign(record, { status: 'archived', version: 2, human_decision: { ...route.request().postDataJSON(), actor: { username: '审核员' }, occurred_at: '2026-09-10' } })
      return route.fulfill({ json: { review: record } })
    }
    return route.fulfill({ status: 404, json: { detail: 'unexpected request' } })
  })
  await page.route('**/__scheduler_review_test__', route => route.fulfill({ contentType: 'text/html', body: `<div id="app" data-scheduler="true" style="height:900px"></div><script type="module" src="/e2e/taskReviewHarness.js"></script>` }))
  await page.goto('/__scheduler_review_test__')
  await expect(page.locator('.task-card')).toHaveCount(2)
  await page.getByRole('button', { name: '工单审核 1', exact: true }).click()
  await expect(page.locator('.task-card')).toHaveCount(1)
  await page.getByRole('button', { name: '查看研判结果' }).click()
  await page.getByLabel('审核意见', { exact: true }).fill('已核验')
  await page.getByRole('button', { name: '确认归档' }).click()
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(page.locator('.task-card')).toHaveCount(1)
  await expect(page.locator('.task-card')).toContainText('站点告警需确认')
  await page.getByRole('button', { name: '事件任务 1', exact: true }).click()
  await expect(page.locator('.task-card')).toContainText('告警研判')
  await page.getByRole('button', { name: '定时任务 1', exact: true }).click()
  await expect(page.locator('.task-card')).toContainText('定时巡检')
  expect(errors).toEqual([])
})
