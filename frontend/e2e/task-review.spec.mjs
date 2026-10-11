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

test('scheduler classifies generic todos by task type and keeps archived items visible', async ({ page }) => {
  const today = new Date().toISOString()
  const records = [
    { ...structuredClone(base), updated_at: today },
    { ...structuredClone(base), review_id: 'review_789', title: '恒值异常需确认', updated_at: today },
    { ...structuredClone(base), review_id: 'review_456', category: '智能事件', title: '站点告警需确认', updated_at: today },
  ]
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/scheduled-tasks')) return route.fulfill({ json: [{ task: { task_id: 'scheduled', name: '定时巡检', trigger_type: 'schedule', enabled: true } }, { task: { task_id: 'event', name: '告警研判', trigger_type: 'event', enabled: true } }] })
    // 真实后端 pending_only=false：列表返回全部状态（含已归档/已退回），由前端状态筛选聚焦。
    if (url.pathname.endsWith('/task-reviews')) return route.fulfill({ json: { reviews: records, total: records.length } })
    const record = records.find(record => url.pathname.includes(record.review_id))
    if (record) {
      if (route.request().method() === 'POST') Object.assign(record, { status: 'archived', version: 2, human_decision: { ...route.request().postDataJSON(), actor: { username: '审核员' }, occurred_at: '2026-09-10' } })
      return route.fulfill({ json: { review: record } })
    }
    return route.fulfill({ status: 404, json: { detail: 'unexpected request' } })
  })
  await page.route('**/__scheduler_review_test__', route => route.fulfill({ contentType: 'text/html', body: `<div id="app" data-scheduler="true" style="height:900px"></div><script type="module" src="/e2e/taskReviewHarness.js"></script>` }))
  await page.goto('/__scheduler_review_test__')
  // 调度中心只渲染结构化审核结果列表：无页签、无统计看板；任务类型筛选默认故障工单审核（category=工单审核）。
  const reviewRows = page.locator('.review-list tbody tr')
  await expect(reviewRows).toHaveCount(2)
  await expect(reviewRows.first()).toContainText('故障处理需确认')
  await expect(reviewRows.first()).not.toContainText('SOP-01')
  await expect(page.locator('.status-grid, .scheduler-tabs, .task-cards-grid, .section-header')).toHaveCount(0)
  await page.getByLabel('任务类型').selectOption('智能事件')
  await expect(reviewRows).toHaveCount(1)
  await expect(reviewRows.first()).toContainText('站点告警需确认')
  await page.getByLabel('任务类型').selectOption('工单审核')
  await expect(reviewRows).toHaveCount(2)
  await page.getByRole('button', { name: '查看详情' }).first().click()
  await page.getByLabel('审核意见', { exact: true }).fill('已核验')
  await page.getByRole('button', { name: '确认归档' }).click()
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  // 归档后记录保留在列表中并显示"已归档"徽章；状态筛选可聚焦待办/已归档。
  // （label 文本含 option 文本，getByLabel exact 匹配不到，用 combobox 角色定位。）
  const statusFilter = page.getByRole('combobox', { name: '状态' })
  await expect(reviewRows).toHaveCount(2)
  await expect(reviewRows.first()).toContainText('已归档')
  await statusFilter.selectOption('archived')
  await expect(reviewRows).toHaveCount(1)
  await expect(reviewRows.first()).toContainText('故障处理需确认')
  await statusFilter.selectOption('pending')
  await expect(reviewRows).toHaveCount(1)
  await expect(reviewRows.first()).toContainText('恒值异常需确认')
  await statusFilter.selectOption('')
  await expect(reviewRows).toHaveCount(2)
  // 已归档记录的详情为只读：无人工处理表单，展示人工处理记录。
  await page.getByRole('button', { name: '查看详情' }).first().click()
  await expect(page.getByRole('heading', { name: '人工处理记录' })).toBeVisible()
  await expect(page.getByRole('button', { name: '确认归档' })).toHaveCount(0)
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  expect(errors).toEqual([])
})

test('scheduler defaults completion-date filter to the last three days', async ({ page }) => {
  const daysAgo = n => new Date(Date.now() - n * 86_400_000).toISOString()
  const records = [
    { ...structuredClone(base), title: '今日完成需确认', updated_at: daysAgo(0) },
    { ...structuredClone(base), review_id: 'review_789', title: '四天前完成需确认', updated_at: daysAgo(4) },
  ]
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/task-reviews')) return route.fulfill({ json: { reviews: records, total: records.length } })
    return route.fulfill({ status: 404, json: { detail: 'unexpected request' } })
  })
  await page.route('**/__scheduler_default_dates__', route => route.fulfill({ contentType: 'text/html', body: `<div id="app" data-scheduler="true" style="height:900px"></div><script type="module" src="/e2e/taskReviewHarness.js"></script>` }))
  await page.goto('/__scheduler_default_dates__')
  // 完成日期默认近三日（含今天）：4 天前的审核结果默认隐藏，把开始日期放宽到 4 天前才出现。
  const reviewRows = page.locator('.review-list tbody tr')
  await expect(reviewRows).toHaveCount(1)
  await expect(reviewRows.first()).toContainText('今日完成需确认')
  const localDay = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  const start = new Date(); start.setDate(start.getDate() - 2)
  const dates = page.locator('.filter-bar input[type="date"]')
  await expect(dates.nth(0)).toHaveValue(localDay(start))
  await expect(dates.nth(1)).toHaveValue(localDay(new Date()))
  const fourDaysAgo = new Date(); fourDaysAgo.setDate(fourDaysAgo.getDate() - 4)
  await dates.nth(0).fill(localDay(fourDaysAgo))
  await expect(reviewRows).toHaveCount(2)
  expect(errors).toEqual([])
})
