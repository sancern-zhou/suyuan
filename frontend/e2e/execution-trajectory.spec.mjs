import { expect, test } from 'playwright/test'

test('opens detailed trajectory only on request, searches history and updates live tool results', async ({ page }) => {
  const messages = [
    { id: 'user', type: 'user', content: '查询空气质量', sequence_number: 1 },
    { id: 'thought', type: 'thought', content: '先核验监测数据的时间范围', sequence_number: 2 },
    { id: 'call', type: 'tool_use', content: 'Tool Use: air_quality', sequence_number: 3, data: { tool_use_id: 'call-1', tool_name: 'air_quality', input: { city: '南昌' } } },
    { id: 'result', type: 'tool_result', sequence_number: 4, data: { tool_use_id: 'call-1', result: { value: 42 } } },
    { id: 'answer', type: 'final', content: '查询完成', sequence_number: 5, data: { response_duration_ms: 6000 } }
  ]
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path.endsWith('/auth/runtime-config')) return route.fulfill({ json: { authMode: 'mock', sysCode: 'SUYUAN', mockUser: { id: 'e2e', userName: 'e2e', name: 'E2E', roleCodes: ['SUYUAN_ADMIN'], isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN' } } })
    if (path.endsWith('/restore')) return route.fulfill({ json: { session: { session_id: 'trajectory-test', source: 'web', mode: 'assistant', conversation_history: messages, has_more_messages: false, total_message_count: 5, oldest_sequence: 1 } } })
    if (path.endsWith('/messages')) return route.fulfill({ json: { messages: url.searchParams.has('before') ? [{ id: 'older', type: 'thought', content: '历史思考记录', sequence_number: 0 }] : messages, has_more: !url.searchParams.has('before'), oldest_sequence: url.searchParams.has('before') ? 0 : 1 } })
    if (path.endsWith('/resources')) return route.fulfill({ json: { resources: [], total: 0, resource_version: 0 } })
    return route.fulfill({ json: { sessions: [], stats: {}, tasks: [], items: [], data: [] } })
  })
  await page.goto('/session/trajectory-test')
  await expect(page.locator('.trajectory-panel')).toHaveCount(0)
  await expect(page.locator('.process-collapse, .live-process-details')).toHaveCount(0)
  const summary = page.getByRole('button', { name: /用时6.0 秒完成 · 1个工具调用/ })
  await expect(summary).toBeVisible()
  await expect(summary.locator('svg circle')).toHaveCount(1)
  await expect(page.locator('.agent-message-duration')).toHaveCount(0)
  await expect(page.locator('.assistant-thought-content')).toHaveCount(0)
  await summary.click()
  await expect(summary).toHaveAttribute('aria-expanded', 'true')
  await expect(page.locator('.assistant-thought-content')).toContainText('先核验监测数据的时间范围')
  await expect(page.locator('.assistant-thought-content')).not.toContainText('air_quality')
  await summary.click()
  await expect(page.locator('.assistant-thought-content')).toHaveCount(0)
  await page.getByRole('button', { name: '查看调用轨迹', exact: true }).click()
  await page.getByRole('button', { name: '执行记录', exact: true }).click()
  const panel = page.locator('.trajectory-panel')
  await expect(panel).toBeVisible()
  await expect(page.getByRole('tab', { name: '调用轨迹', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('tab', { name: '文件产物', exact: true })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: '工作流', exact: true })).toHaveCount(0)
  await expect(page.locator('.trajectory-tab-bar')).toHaveCount(0)
  await expect(panel.locator('details')).toHaveCount(4)
  await panel.getByRole('button', { name: '全部展开' }).click()
  await expect(panel).toContainText('南昌')
  await expect(panel).toContainText('42')
  await panel.getByRole('button', { name: '加载更早的轨迹' }).click()
  await panel.getByRole('searchbox').fill('历史思考')
  await expect(panel.locator('details')).toHaveCount(1)
  await expect(panel).toContainText('历史思考记录')
  await panel.getByRole('searchbox').fill('')
  await page.evaluate(async () => {
    const { useReactStore } = await import('/src/stores/reactStore.js')
    useReactStore().currentState.messages.push(
      { id: 'live-call', type: 'tool_use', sequence_number: 6, data: { tool_use_id: 'live', tool_name: 'live_query', input: { city: '赣州' } } },
      { id: 'live-result', type: 'tool_result', sequence_number: 7, data: { tool_use_id: 'live', result: { error: '查询失败' }, is_error: true } }
    )
  })
  await expect(panel).toContainText('live_query')
  await expect(panel).toContainText('查询失败')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(panel).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('trajectory-mobile.png') })
  await panel.getByRole('button', { name: '模型调用', exact: true }).click()
  await expect(page.locator('.model-trajectory-panel')).toBeVisible()
  await page.evaluate(async () => {
    const { useReactStore } = await import('/src/stores/reactStore.js')
    const state = useReactStore().currentState
    state.isAnalyzing = true
    state.messages.push(
      { id: 'new-question', type: 'user', content: '继续查询', sequence_number: 8 },
      { id: 'live-thought', type: 'thought', content: '正在核验新增记录', streaming: true, sequence_number: 9 }
    )
  })
  await expect(page.locator('.assistant-live-thoughts')).toBeVisible()
  await expect(page.locator('.assistant-live-thoughts .assistant-thought-content')).not.toBeVisible()
  await page.locator('.assistant-live-thoughts summary').click()
  await expect(page.locator('.assistant-live-thoughts .assistant-thought-content')).toContainText('正在核验新增记录')
  await page.evaluate(async () => {
    const { useReactStore } = await import('/src/stores/reactStore.js')
    useReactStore().currentState.messages.at(-1).content += '，继续检查时间一致性'
  })
  await expect(page.locator('.assistant-live-thoughts .assistant-thought-content')).toContainText('继续检查时间一致性')
})
