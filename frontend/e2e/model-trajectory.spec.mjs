import { expect, test } from 'playwright/test'

test('model cards expose full inputs, responses, usage and searchable virtualized history', async ({ page }) => {
  const records = Array.from({ length: 60 }, (_, index) => ({
    request_id: String(index + 1).padStart(3, '0'), session_id: 'model-test', source: index === 59 ? 'compact' : 'main',
    status: 'completed', provider: 'fixture', model: 'fixture-model', duration_ms: 1200, started_at: '2026-10-06T01:00:00Z',
    request: { system: 'system instructions', messages: [{ role: 'user', content: `request ${index}` }] },
    response: { content: [{ type: 'thinking', thinking: `thinking ${index}` }, { type: 'tool_use', id: `call-${index}`, name: 'query_weather', input: { city: index === 59 ? 'special-match-南昌' : '赣州' } }], usage: { input_tokens: 20, output_tokens: 5, cache_read_input_tokens: 3 }, stop_reason: 'tool_use' }
  }))
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path.endsWith('/auth/runtime-config')) return route.fulfill({ json: { authMode: 'mock', sysCode: 'SUYUAN', mockUser: { id: 'e2e', userName: 'e2e', name: 'E2E', roleCodes: ['SUYUAN_ADMIN'], isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN' } } })
    if (path.endsWith('/restore')) return route.fulfill({ json: { session: { session_id: 'model-test', source: 'web', mode: 'assistant', conversation_history: [{ id: 'u', type: 'user', content: 'query', sequence_number: 1 }, { id: 'a', type: 'final', content: 'done', sequence_number: 2 }], has_more_messages: false, total_message_count: 2, oldest_sequence: 1 } } })
    if (path.endsWith('/model-trajectory')) return route.fulfill({ json: { records, total_count: records.length, has_more: false, oldest_request_id: '001' } })
    if (path.endsWith('/resources')) return route.fulfill({ json: { resources: [], total: 0, resource_version: 0 } })
    return route.fulfill({ json: { messages: [], sessions: [], stats: {}, tasks: [], items: [], data: [] } })
  })
  await page.goto('/session/model-test')
  await expect(page.locator('.viz-wrapper')).toHaveCount(0)
  await expect(page.locator('.width-resizer')).toHaveCount(0)
  await page.getByRole('button', { name: '查看调用轨迹', exact: true }).click()
  const panel = page.locator('.model-trajectory-panel')
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('60 次调用')
  await expect(panel).toContainText('fixture-model')
  await expect(panel.locator('.model-call-card').first()).toContainText('输入 20 · 输出 5 · 缓存 3 Token')
  expect(await panel.locator('.model-call-card').count()).toBeLessThan(60)
  const timeline = panel.locator('.model-timeline')
  const dimensions = await timeline.evaluate(element => ({ height: element.clientHeight, content: element.scrollHeight, bottom: element.getBoundingClientRect().bottom, overflow: getComputedStyle(element).overflowY }))
  expect(dimensions.height).toBeGreaterThan(100)
  expect(dimensions.content).toBeGreaterThan(dimensions.height)
  expect(dimensions.bottom).toBeLessThanOrEqual(page.viewportSize().height)
  expect(dimensions.overflow).toBe('scroll')
  await timeline.hover()
  await page.mouse.wheel(0, 600)
  await expect.poll(() => timeline.evaluate(element => element.scrollTop)).toBeGreaterThan(0)
  await timeline.evaluate(element => { element.scrollTop = 0 })
  await panel.getByRole('button', { name: '思考', exact: true }).click()
  await expect(panel.locator('pre').first()).toContainText('thinking')
  await panel.getByRole('searchbox').fill('special-match-南昌')
  await expect(panel.locator('.model-call-card[data-call-id="060"]')).toBeVisible()
  await expect(panel.locator('.search-active mark')).toHaveText('special-match-南昌')
  await expect(panel.locator('.model-call-card[data-call-id="060"]')).toContainText('上下文压缩')
  await panel.getByRole('searchbox').fill('')
  await panel.getByRole('button', { name: '全部展开' }).click()
  await expect(panel.locator('pre').filter({ hasText: 'system instructions' }).first()).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('model-trajectory.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(panel).toBeVisible()
  expect(await timeline.evaluate(element => element.getBoundingClientRect().bottom)).toBeLessThanOrEqual(844)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('empty sessions do not reserve a right panel and removing content releases its width', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path.endsWith('/auth/runtime-config')) return route.fulfill({ json: { authMode: 'mock', sysCode: 'SUYUAN', mockUser: { id: 'e2e', userName: 'e2e', name: 'E2E', roleCodes: ['SUYUAN_ADMIN'], isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN' } } })
    if (path.endsWith('/restore')) return route.fulfill({ json: { session: { session_id: 'empty-panel', source: 'web', mode: 'assistant', conversation_history: [{ id: 'question', type: 'user', content: 'hello', sequence_number: 1 }], has_more_messages: false, total_message_count: 1 } } })
    if (path.endsWith('/resources')) return route.fulfill({ json: { resources: [], total: 0, resource_version: 0 } })
    return route.fulfill({ json: { workflows: [], records: [], sessions: [], stats: {}, tasks: [], items: [], data: [] } })
  })
  await page.goto('/session/empty-panel')
  await expect(page.locator('.viz-wrapper')).toHaveCount(0)
  await expect(page.locator('.viz-toggle-btn')).toHaveCount(0)
  const workspace = page.locator('.conversation-workspace')
  const initialWidth = await workspace.evaluate(element => element.clientWidth)
  await page.evaluate(async () => {
    const { useReactStore } = await import('/src/stores/reactStore.js')
    useReactStore().currentState.messages.push({ id: 'answer', type: 'final', content: 'done', sequence_number: 1 })
  })
  await expect(page.locator('.viz-toggle-btn')).toBeVisible()
  await expect(page.locator('.viz-wrapper')).toHaveCount(0)
  await page.locator('.viz-toggle-btn').click()
  await expect(page.locator('.model-trajectory-panel')).toBeVisible()
  await expect(page.getByRole('tab', { name: '文件产物', exact: true })).toHaveCount(0)
  expect(await workspace.evaluate(element => element.clientWidth)).toBeLessThan(initialWidth)
  await page.evaluate(async () => {
    const { useReactStore } = await import('/src/stores/reactStore.js')
    useReactStore().currentState.messages = []
  })
  await expect(page.locator('.viz-wrapper')).toHaveCount(0)
  await expect(page.locator('.viz-toggle-btn')).toHaveCount(0)
  await expect.poll(() => workspace.evaluate(element => element.clientWidth)).toBeGreaterThanOrEqual(initialWidth)
})
