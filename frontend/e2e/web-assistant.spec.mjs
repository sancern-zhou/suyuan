import { test, expect } from 'playwright/test'

test.use({ channel: process.env.PLAYWRIGHT_CHANNEL })

async function application(page, { conflict = false } = {}) {
  page.on('pageerror', error => console.error('Application error:', error.message))
  const calls = []
  const task = { task_id: 'task-1', goal: '核查现场停产反馈', completion_criteria: '形成有依据的核查结论',
    status: 'waiting_input', next_step: '等待现场反馈', version: 1, source_session_id: 'web-e2e', events: [] }
  const suggestion = { suggestion_id: 'suggestion-1', goal: '整理会商材料', reason: '已有分析可整理为汇报提纲',
    suggested_prompt: '根据已有结论整理会商提纲', missing_inputs: ['会商日期'], state: 'pending', version: 1, source_session_id: 'web-e2e' }
  await page.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path.endsWith('/auth/runtime-config')) return route.fulfill({ json: {
      authMode: 'mock', sysCode: 'SUYUAN', mockUser: { id: 'alice', userName: 'alice', name: 'Alice', roleCodes: ['SUYUAN_ADMIN'], isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN' }
    } })
    if (path.endsWith('/sessions/web-e2e/restore')) return route.fulfill({ json: { session: {
      session_id: 'web-e2e', source: 'web', mode: 'social', read_only_on_web: false,
      conversation_history: [{ id: 'message-1', type: 'user', role: 'user', content: '请持续核查现场反馈' }],
      metadata: { mode: 'social' }, resource_counts: { total: 0 }, resource_version: 1
    } } })
    if (path.endsWith('/agent/analyze')) {
      calls.push({ path, body: req.postDataJSON() })
      return route.fulfill({ contentType: 'text/event-stream', body:
        'data: {"type":"start","data":{"session_id":"web-e2e","mode":"social"}}\n\n' +
        'data: {"type":"complete","data":{"answer":"已收到，继续处理已有事项。","session_id":"web-e2e"}}\n\n' })
    }
    if (/\/assistant\/tasks\/task-1\/actions$/.test(path)) {
      const body = req.postDataJSON(); calls.push({ path, body })
      if (conflict) return route.fulfill({ status: 409, json: { detail: 'Version changed' } })
      task.version++
      if (body.action === 'feedback') { task.events.push({ event_id: 'event-1', user_message: body.text, created_at: '2026-10-19T01:00:00' }); task.next_step = '反馈已保存' }
      if (body.action === 'cancel') task.status = 'cancelled'
      return route.fulfill({ json: { task } })
    }
    if (/\/assistant\/suggestions\/suggestion-1\/actions$/.test(path)) {
      const body = req.postDataJSON(); calls.push({ path, body })
      suggestion.state = body.action === 'accept' ? 'accepted' : 'dismissed'; suggestion.version++
      return route.fulfill({ json: { suggestion, execution_state: 'not_started', next_action: { kind: 'tool', target: 'create_report_package' } } })
    }
    if (path.endsWith('/assistant/tasks/task-1')) return route.fulfill({ json: { task } })
    if (path.endsWith('/assistant/tasks')) return route.fulfill({ json: { tasks: [task] } })
    if (path.endsWith('/assistant/suggestions')) return route.fulfill({ json: { suggestions: [suggestion] } })
    if (path.endsWith('/assistant/notifications')) return route.fulfill({ json: { notifications: [
      { message_id: 'notice-1', task_id: 'task-1', content: '请关注现场反馈', created_at: '2026-10-19T01:00:00' }
    ] } })
    if (path.endsWith('/sessions/web-e2e/resources')) return route.fulfill({ json: { session_id: 'web-e2e', resources: [], total: 0, resource_version: 1, next_cursor: null } })
    return route.fulfill({ json: { tasks: [], sessions: [], items: [], data: [], stats: {} } })
  })
  await page.goto('/session/web-e2e')
  await expect(page.getByRole('button', { name: '事项与建议', exact: true })).toBeVisible()
  return calls
}

test('restores social-backed Web assistant, posts feedback with version, and shows reminder detail', async ({ page }) => {
  const calls = await application(page)
  await page.getByRole('button', { name: '事项与建议', exact: true }).click()
  const panel = page.getByRole('complementary', { name: '我的助理' })
  await expect(panel.getByRole('heading', { name: '核查现场停产反馈' })).toBeVisible()
  await panel.getByRole('button', { name: '补充反馈' }).click()
  await panel.getByLabel('现场反馈').fill('现场已确认停产')
  await panel.getByRole('button', { name: '保存反馈' }).click()
  await expect(panel.getByRole('status')).toHaveText('反馈已保存')
  expect(calls[0].body).toEqual({ action: 'feedback', text: '现场已确认停产', expected_version: 1 })
  await panel.getByRole('button', { name: '提醒', exact: true }).click()
  await expect(panel.getByText('请关注现场反馈')).toBeVisible()
  await panel.getByRole('button', { name: '查看事项' }).click()
  await expect(panel.getByText('形成有依据的核查结论')).toBeVisible()
  await page.screenshot({ path: 'test-results/web-assistant-desktop.png', fullPage: true })
})

test('accepting a suggestion records a choice; explicit continuation uses social runtime', async ({ page }) => {
  const calls = await application(page)
  await page.getByRole('button', { name: '事项与建议', exact: true }).click()
  const panel = page.getByRole('complementary', { name: '我的助理' })
  await panel.getByRole('button', { name: '建议', exact: true }).click()
  await panel.getByRole('button', { name: '采纳', exact: true }).click()
  await expect(panel.getByRole('status')).toHaveText('已采纳，尚未开始执行')
  expect(calls.filter(call => call.path.endsWith('/agent/analyze'))).toHaveLength(0)
  await panel.getByRole('button', { name: '继续讨论' }).click()
  await expect.poll(() => calls.filter(call => call.path.endsWith('/agent/analyze')).length).toBe(1)
  expect(calls.find(call => call.path.endsWith('/agent/analyze')).body.mode).toBe('social')
})

test('mobile assistant fits the viewport and exposes conflicts without claiming success', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await application(page, { conflict: true })
  await page.getByRole('button', { name: '事项与建议', exact: true }).click()
  const panel = page.getByRole('complementary', { name: '我的助理' })
  await panel.getByRole('button', { name: '取消事项' }).click()
  await expect(panel.getByRole('alert')).toContainText('事项已变化')
  await expect(panel.getByRole('status')).toHaveCount(0)
  const box = await panel.boundingBox()
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(390)
  expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/web-assistant-mobile.png', fullPage: true })
})

test('personal assistant does not expose the old shared mode-memory editor', async ({ page }) => {
  await application(page)
  await page.getByRole('button', { name: '更多功能' }).click()
  await expect(page.getByRole('menuitem', { name: '查看模式记忆' })).toHaveCount(0)
})
