import { expect, test } from 'playwright/test'
import { readFile } from 'node:fs/promises'

const history = Array.from({ length: 24 }, (_, index) => ({
  id: `message-${index}`,
  type: index % 2 ? 'final' : 'user',
  role: index % 2 ? 'assistant' : 'user',
  content: `Message ${index}\n\n${'A paragraph of conversation content. '.repeat(12)}`,
  sequence_number: index + 30
}))

async function openChat(page, hasMore = false) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path.endsWith('/auth/runtime-config')) {
      return route.fulfill({ json: { authMode: 'mock', sysCode: 'SUYUAN', mockUser: {
        id: 'e2e', userName: 'e2e', name: 'E2E', roleCodes: ['SUYUAN_ADMIN'],
        isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN'
      } } })
    }
    if (path.endsWith('/restore')) {
      return route.fulfill({ json: { session: {
        session_id: 'scroll-test', source: 'web', mode: 'assistant',
        conversation_history: history, has_more_messages: hasMore,
        total_message_count: hasMore ? 30 : 24, oldest_sequence: 30
      } } })
    }
    if (path.endsWith('/resources')) {
      return route.fulfill({ json: { resources: [], total: 0, resource_version: 0 } })
    }
    return route.fulfill({ json: { sessions: [], stats: {}, tasks: [], items: [], data: [] } })
  })
  await page.goto('/session/scroll-test')
  await expect(page.locator('.message-wrapper')).toHaveCount(24)
  await expectBottom(page)
}

async function expectBottom(page) {
  await expect.poll(() => page.locator('.react-message-list').evaluate(
    el => Math.abs(el.scrollHeight - el.scrollTop - el.clientHeight)
  )).toBeLessThanOrEqual(2)
}

async function appendReply(page, content, waitForGrowth = true) {
  const previousHeight = await page.locator('.react-message-list').evaluate(el => el.scrollHeight)
  await page.evaluate(async content => {
    const { useReactStore } = await import('/src/stores/reactStore.js')
    const message = useReactStore().currentState.messages.at(-1)
    message.streaming = true
    message.content += content
  }, content)
  if (waitForGrowth) {
    await expect.poll(() => page.locator('.react-message-list').evaluate(el => el.scrollHeight)).toBeGreaterThan(previousHeight)
  }
}

for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 700 }]) {
  test.describe(`${viewport.width}px chat scrolling`, () => {
    test.use({ viewport })

    test('follows streamed text, delayed images and composer/viewport resizing', async ({ page }) => {
      await openChat(page)
      for (let index = 0; index < 3; index++) {
        await appendReply(page, `\n\n${'Streamed response. '.repeat(80)}`)
        await expectBottom(page)
      }

      let releaseImage
      const imageReady = new Promise(resolve => { releaseImage = resolve })
      const imageBytes = await readFile(new URL('../public/wechat-screenshot.png', import.meta.url))
      await page.route('**/scroll-image.png', async route => {
        await imageReady
        await route.fulfill({ contentType: 'image/png', body: imageBytes })
      })
      await appendReply(page, '\n\n![Delayed image](/scroll-image.png)', false)
      await page.evaluate(async () => {
        const { useReactStore } = await import('/src/stores/reactStore.js')
        useReactStore().currentState.messages.at(-1).streaming = false
      })
      const image = page.locator('.message-wrapper').last().locator('img')
      await expect(image).toHaveCount(1)
      releaseImage()
      await expect.poll(() => image.evaluate(el => el.naturalHeight)).toBeGreaterThan(0)
      await expectBottom(page)

      await page.locator('textarea').fill('Line one\nLine two\nLine three\nLine four\nLine five\nLine six')
      await expectBottom(page)
      await page.setViewportSize({ width: viewport.width, height: viewport.height - 180 })
      await expectBottom(page)
      const bounds = await page.locator('.input-area').boundingBox()
      expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height - 180 + 1)
      await page.screenshot({ path: test.info().outputPath('chat-bottom.png') })
    })

    test('keeps history in place until the user returns to the bottom', async ({ page }) => {
      await openChat(page)
      const list = page.locator('.react-message-list')
      await list.hover()
      await page.mouse.wheel(0, -500)
      await expect(page.getByTitle('回到底部', { exact: true })).toBeVisible()
      const top = await list.evaluate(el => el.scrollTop)
      await appendReply(page, `\n\n${'More streamed text. '.repeat(100)}`)
      await page.waitForTimeout(2200)
      await appendReply(page, '\n\nStill streaming after the old timeout.')
      await expect.poll(() => list.evaluate(el => el.scrollTop)).toBe(top)

      await page.getByTitle('回到底部', { exact: true }).click()
      await expectBottom(page)
      await expect(page.getByTitle('回到底部', { exact: true })).toHaveCount(0)
      await appendReply(page, `\n\n${'Continue following. '.repeat(50)}`)
      await expectBottom(page)
    })

    test('preserves the visible message when earlier history is prepended', async ({ page }) => {
      await openChat(page, true)
      let releaseHistory
      const historyReady = new Promise(resolve => { releaseHistory = resolve })
      await page.route('**/sessions/scroll-test/messages?**', async route => {
        await historyReady
        await route.fulfill({ json: {
          messages: history.slice(0, 6).map((message, index) => ({
            ...message, id: `earlier-${index}`, content: `Earlier ${index}\n\n${message.content}`,
            sequence_number: index
          })), has_more: false, total_count: 30
        } })
      })
      const list = page.locator('.react-message-list')
      const before = await page.locator('.message-wrapper').first().evaluate(
        el => el.getBoundingClientRect().y + el.closest('.react-message-list').scrollTop
      )
      await list.evaluate(el => { el.scrollTop = 0 })
      await expect(page.locator('.loading-indicator')).toBeVisible()
      releaseHistory()
      await expect(page.locator('.message-wrapper')).toHaveCount(30)
      await expect.poll(async () => (await page.locator('.message-wrapper').nth(6).boundingBox()).y).toBeCloseTo(before, 0)
    })

    test('switching sessions with equal message counts resets to the bottom', async ({ page }) => {
      await openChat(page)
      await page.locator('.react-message-list').evaluate(el => { el.scrollTop = 100 })
      await expect(page.getByTitle('回到底部', { exact: true })).toBeVisible()
      await page.evaluate(async () => {
        const { useReactStore } = await import('/src/stores/reactStore.js')
        const state = useReactStore().currentState
        state.sessionId = 'next-session'
        state.messages = state.messages.map(message => ({ ...message, id: `next-${message.id}` }))
      })
      await expectBottom(page)
    })
  })
}
