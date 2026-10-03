import { expect, test } from 'playwright/test'

const definitions = [
  { task_id: 'monitoring', title: '监测数据', target_mode: 'query_monitoring', goal: '获取并检查监测数据' },
  { task_id: 'weather', title: '气象数据', target_mode: 'query_forecast', goal: '获取同期气象数据' },
  { task_id: 'analysis', title: '污染分析', target_mode: 'expert_analysis', goal: '分析污染变化与成因', dependencies: ['monitoring', 'weather'] }
]
const graph = Object.fromEntries(definitions.map(node => [node.task_id, { status: 'succeeded', dependencies: node.dependencies || [] }]))
const workflow = {
  workflow_id: 'workflow-review', status: 'succeeded', job_status: 'succeeded', active: false,
  snapshot: {
    status: 'succeeded', graph,
    definition: { nodes: definitions.map(node => ({ task_id: node.task_id, dependencies: node.dependencies || [], payload: { title: node.title, target_mode: node.target_mode, goal: node.goal } })) },
    runtime: { events: [{ sequence: 1, task_id: 'analysis', event_type: 'task.running', timestamp: '2026-10-03T08:00:00Z' }, { sequence: 2, task_id: 'analysis', event_type: 'task.succeeded', timestamp: '2026-10-03T08:00:12Z' }] }
  }
}

test('workflow is an ordered list and child agent opens in a review view', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path.endsWith('/auth/runtime-config')) return route.fulfill({ json: { authMode: 'mock', sysCode: 'SUYUAN', mockUser: { id: 'e2e', userName: 'e2e', name: 'E2E', roleCodes: ['SUYUAN_ADMIN'], isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN' } } })
    if (path.endsWith('/restore')) return route.fulfill({ json: { session: { session_id: 'workflow-review', source: 'web', mode: 'report', conversation_history: [{ id: 'message-1', type: 'final', role: 'assistant', content: '分析完成', sequence_number: 1 }], has_more_messages: false, total_message_count: 1, oldest_sequence: 1 } } })
    if (path.endsWith('/resources')) return route.fulfill({ json: { resources: [], total: 0, resource_version: 0 } })
    if (path.endsWith('/workflows')) return route.fulfill({ json: { workflows: [workflow], total: 1 } })
    if (path.endsWith('/events')) return route.fulfill({ json: { events: [] } })
    if (path.endsWith('/nodes/analysis/history')) return route.fulfill({ json: {
      task_id: 'analysis', status: 'succeeded', child_session_id: 'report__to__expert__1', child_mode: 'expert_analysis',
      conversation: [{ id: 'q', role: 'user', content: '分析污染变化与成因' }, { id: 'a', role: 'assistant', content: 'PM2.5 在静稳时段明显累积。' }],
      node_events: [{ sequence: 1, type: 'task.running', status: 'running', timestamp: '2026-10-03T08:00:00Z' }], child_events: [],
      execution_history: [{ sequence: 1, type: 'tool_call', tool_name: 'air_quality' }, { sequence: 2, type: 'tool_result', tool_name: 'air_quality', success: true }], has_more: false
    } })
    return route.fulfill({ json: { sessions: [], stats: {}, tasks: [], items: [], data: [] } })
  })

  await page.goto('/session/workflow-review')
  await page.locator('.viz-toggle-btn').click()
  await page.getByRole('tab', { name: '工作流', exact: true }).click()

  await expect(page.locator('.workflow-stage')).toHaveCount(2)
  await expect(page.locator('.workflow-stage').first()).toContainText('并行 2 个节点')
  await expect(page.locator('.workflow-stage').nth(1)).toContainText('上游：监测数据、气象数据')
  await expect(page.locator('.workflow-panel svg')).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('workflow-list.png') })

  await page.getByRole('button', { name: /污染分析/ }).click()
  await expect(page.getByRole('article', { name: '子 Agent 对话审查' })).toBeVisible()
  await expect(page.getByText('PM2.5 在静稳时段明显累积。')).toBeVisible()
  await expect(page.getByText('调用 air_quality')).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('subagent-review.png') })

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('article', { name: '子 Agent 对话审查' })).toBeVisible()
  expect((await page.locator('.workflow-panel').boundingBox()).width).toBeGreaterThanOrEqual(300)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('subagent-review-mobile.png') })

  await page.getByRole('button', { name: '执行列表' }).click()
  await expect(page.locator('.workflow-stage-list')).toBeVisible()
})
