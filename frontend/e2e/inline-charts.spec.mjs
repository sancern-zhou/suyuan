import { expect, test } from 'playwright/test'

const imageId = 'a'.repeat(32)
const specId = 'b'.repeat(32)
const previewId = 'c'.repeat(32)
const unknownId = 'd'.repeat(32)
const sessionId = 'chart-session'
const shareId = 'chart-share'
const ref = id => `[[chart:${id}]]`
const resources = (scope, owner) => [
  [imageId, 'primary:png', '图片图表', 'image', 'image/png', 'static'],
  [specId, 'chart-spec', '交互图表', 'chart', 'application/json', 'interactive'],
  [previewId, 'chart-image', '可选预览', 'image', 'image/png', 'interactive']
].map(([resource_id, resource_key, label, renderer, media_type, group_id]) => ({
  resource_id, resource_key, label, renderer, media_type, group_id, status: 'active',
  content_url: `/api/${scope}/${owner}/resources/${resource_id}/content?preview_ticket=snapshot`
}))
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64')
const reply = [
  `\`${ref(unknownId)}\``,
  `~~~text\n${ref(unknownId)}\n~~~`,
  `分析开始\n\n${ref(imageId)}\n\n分析中段\n\n${ref(specId)}\n\n分析结束`,
  ref(unknownId),
  ref('chart_1')
].join('\n\n')

async function mockApp(page, content = reply) {
  const requests = []
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/auth/runtime-config')) {
      return route.fulfill({ json: { authMode: 'mock', sysCode: 'SUYUAN', mockUser: {
        id: 'e2e', userName: 'e2e', name: 'E2E', roleCodes: ['SUYUAN_ADMIN'],
        isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN'
      } } })
    }
    if (url.pathname.endsWith(`/sessions/${sessionId}/restore`)) {
      return route.fulfill({ json: { session: {
        session_id: sessionId, source: 'web', mode: 'assistant', resource_version: 1,
        conversation_history: [
          { id: 'question', type: 'user', content: '查看图表' },
          ...(content ? [{ id: 'answer', type: 'final', content }] : [])
        ]
      } } })
    }
    if (url.pathname.endsWith(`/sessions/${sessionId}/resources`)) {
      return route.fulfill({ json: { resources: resources('sessions', sessionId), resource_version: 1 } })
    }
    if (url.pathname.endsWith('/shared-conversations')) {
      return route.fulfill({ json: { shares: [{ share_id: shareId, title: '共享图表' }] } })
    }
    if (url.pathname.endsWith(`/shared-conversations/${shareId}`)) {
      return route.fulfill({ json: {
        share_id: shareId, title: '共享图表', resources: resources('shared-conversations', shareId),
        messages: [{ type: 'final', content: reply, attachments: [
          { resource_id: imageId, mime_type: 'image/png', filename: '正文图表重复附件',
            url: `/api/shared-conversations/${shareId}/resources/${imageId}/content` },
          { resource_id: 'photo', mime_type: 'image/png', filename: '普通图片附件',
            url: `/api/shared-conversations/${shareId}/resources/photo/content` },
          { resource_id: 'doc', mime_type: 'text/plain', filename: '普通文档附件',
            url: `/api/shared-conversations/${shareId}/resources/doc/content` }
        ] }]
      } })
    }
    if (/\/resources\/[^/]+\/content$/.test(url.pathname)) {
      const id = url.pathname.split('/').at(-2)
      requests.push({ url, id, sysCode: route.request().headers().syscode })
      if (id === specId) return route.fulfill({ json: { type: 'pie', data: [{ name: 'Test', value: 1 }] } })
      return route.fulfill({ body: png, contentType: 'image/png' })
    }
    return route.fulfill({ json: { tasks: [], sessions: [], stats: {}, items: [], data: [] } })
  })
  return requests
}

async function expectInlineReply(body) {
  const image = body.getByRole('img', { name: '图片图表' })
  await expect(image).toBeVisible()
  await expect.poll(() => image.evaluate(img => img.naturalWidth)).toBeGreaterThan(0)
  await expect(body.locator('.inline-chart-card canvas').first()).toBeVisible()
  await expect(body.locator('code')).toHaveText([ref(unknownId), `${ref(unknownId)}\n`])
  await expect(body.getByText('【图表不可用】', { exact: true })).toHaveCount(1)
  await expect(body.getByText(ref('chart_1'), { exact: true })).toBeVisible()
  const chartPositions = await body.locator('.md-chart-slot').evaluateAll(slots => slots
    .filter(slot => slot.querySelector('img, canvas'))
    .map(slot => slot.parentElement.previousElementSibling?.textContent))
  expect(chartPositions).toEqual(['分析开始', '分析中段'])
}

test('restored chat renders exact image and spec members at their references', async ({ page }) => {
  const requests = await mockApp(page)
  await page.goto(`/session/${sessionId}`)
  await expectInlineReply(page.locator('.agent-message .message-content'))
  expect(requests.map(item => item.id).sort()).toEqual([imageId, specId])
  expect(requests.every(item => item.sysCode === 'SUYUAN' && item.url.searchParams.get('preview_ticket') === 'snapshot')).toBe(true)
})

test('terminal text replaces streamed text in the same reply', async ({ page }) => {
  await mockApp(page, '')
  await page.goto(`/session/${sessionId}`)
  await expect(page.locator('.user-message')).toHaveText(/查看图表/)
  const dispatch = (type, data) => page.evaluate(async ({ type, data, sessionId }) => {
    const { useReactStore } = await import('/src/stores/reactStore.js')
    useReactStore().handleEvent({ type, data: { ...data, session_id: sessionId } })
  }, { type, data, sessionId })
  const body = page.locator('.agent-message .message-content')
  await dispatch('streaming_text', { chunk: '正在分析\n\n' })
  await dispatch('streaming_text', { chunk: '[[chart:backend/图表' })
  await expect(body).toContainText('正在分析')
  await dispatch('incomplete', { response: `已经完成的部分\n\n${ref(imageId)}` })
  await expect(body).toHaveCount(1)
  await expect(body).toContainText('已经完成的部分')
  await expect(body).not.toContainText('backend/')
  await expect(body.getByRole('img', { name: '图片图表' })).toBeVisible()
  await expect(body.locator('.streaming-cursor')).toHaveCount(0)
  await dispatch('answer_delta', { delta: '要清除的旧文本' })
  await expect(body.last()).toContainText('要清除的旧文本')
  await dispatch('complete', { response: '' })
  await expect(body.last()).not.toContainText('要清除的旧文本')
  await expect(body.last().locator('.streaming-cursor')).toHaveCount(0)
})

test('share uses snapshot chart content and retains ordinary attachments', async ({ page }) => {
  const requests = await mockApp(page, '')
  await page.goto(`/session/${sessionId}`)
  await expect(page.locator('.user-message')).toHaveText(/查看图表/)
  // The default project omits the sidebar entry. Mount the real panel with the
  // running app context so this test runs under every project configuration.
  await page.evaluate(async () => {
    const [{ createVNode, render }, { default: panel }] = await Promise.all([
      import('/node_modules/.vite/deps/vue.js'),
      import('/src/components/management/SharedConversationsPanel.vue')
    ])
    const host = document.createElement('div')
    document.body.prepend(host)
    const node = createVNode(panel)
    node.appContext = document.querySelector('#app').__vue_app__._context
    render(node, host)
  })
  const panel = page.locator('.shared-conversations-panel')
  await panel.getByRole('button', { name: '共享图表' }).click()
  await expectInlineReply(panel.locator('.message-content'))
  await expect(panel.getByRole('img', { name: '普通图片附件' })).toBeVisible()
  await expect(panel.getByRole('link', { name: /普通文档附件/ })).toBeVisible()
  expect(requests.map(item => item.id).sort()).toEqual([imageId, specId, 'photo'])
  expect(requests.every(item => item.sysCode === 'SUYUAN' && item.url.pathname.includes(`/shared-conversations/${shareId}/`))).toBe(true)
})
