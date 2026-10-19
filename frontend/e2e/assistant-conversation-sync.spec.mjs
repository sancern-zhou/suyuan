import { expect, test } from 'playwright/test'

test.use({ channel: process.env.PLAYWRIGHT_CHANNEL || undefined })

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`assistant shows shared App turns and background replies at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport)
    let revision = 2
    const reads = []
    const messages = () => [
      { id: 'msg_1', sequence_number: 0, type: 'user', role: 'user', content: 'Question sent from App' },
      { id: 'msg_2', sequence_number: 1, type: 'final', role: 'assistant', content: 'Shared assistant reply' },
      ...(revision === 3 ? [{ id: 'msg_3', sequence_number: 2, type: 'final', role: 'assistant', content: 'Scheduled analysis completed' }] : [])
    ]
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url())
      if (!url.pathname.startsWith('/api/')) return route.continue()
      if (url.pathname.endsWith('/auth/runtime-config')) return route.fulfill({ json: {
        authMode: 'mock', sysCode: 'SUYUAN', mockUser: { id: '42', userName: 'alice', name: 'Alice', roleCodes: ['SUYUAN_ADMIN'], isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN' }
      } })
      if (url.pathname.endsWith('/assistant/conversations')) return route.fulfill({ json: { sessions: [
        { session_id: 'shared', mode: 'assistant', title: 'Shared assistant', source: 'web', unread_count: 1, updated_at: new Date().toISOString() }
      ] } })
      if (url.pathname.endsWith('/shared/sync')) return route.fulfill({ json: {
        session_id: 'shared', revision, oldest_sequence: 0, through_sequence: revision - 1,
        messages: messages(), pending_interaction: null
      } })
      if (url.pathname.endsWith('/shared/read')) {
        reads.push(route.request().postDataJSON().through_sequence)
        return route.fulfill({ json: { success: true } })
      }
      if (url.pathname.endsWith('/shared/restore')) return route.fulfill({ json: { session: {
        session_id: 'shared', mode: 'assistant', source: 'web', metadata: {}, conversation_history: messages()
      } } })
      if (url.pathname.endsWith('/shared/resources')) return route.fulfill({ json: { session_id: 'shared', resources: [], total: 0, resource_version: 0 } })
      return route.fulfill({ json: { sessions: [], stats: {}, tasks: [], suggestions: [], data: [] } })
    })
    await page.goto('/session/shared')
    await expect(page.getByText('Shared assistant reply', { exact: true })).toBeVisible()
    revision = 3
    await expect(page.getByText('Scheduled analysis completed', { exact: true })).toBeVisible({ timeout: 15000 })
    await expect.poll(() => reads.includes(2)).toBe(true)
    await expect(page.getByText('Scheduled analysis completed', { exact: true })).toHaveCount(1)
    await page.screenshot({ path: `test-results/assistant-sync-${viewport.width}.png`, fullPage: true, animations: 'disabled' })
  })
}
