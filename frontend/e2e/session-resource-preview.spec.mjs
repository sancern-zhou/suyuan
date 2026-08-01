import { expect, test } from 'playwright/test'

const fixtures = [
  ['DOCX/PDF', 'pdf', 'pdf', 'document', '.resource-preview-host iframe'],
  ['HTML', 'html', 'html', 'document', '.resource-preview-host iframe[sandbox]'],
  ['Markdown', 'md', 'markdown', 'document', '.resource-preview-host .scroll'],
  ['Spreadsheet', 'xlsx', 'spreadsheet', 'document', '.resource-preview-host .sheet'],
  ['Presentation', 'pptx', 'presentation', 'document', '.resource-preview-host .slides'],
  ['Image', 'png', 'image', 'document', '.resource-preview-host .image'],
  ['Chart', 'json', 'chart', 'visualization', '.resource-preview-host .chart'],
  ['Board', 'drawio', 'board', 'board', '.resource-preview-host .board']
]

const tabLabel = { document: '文档', visualization: '可视化', board: '画板' }

function resourceFixture([name, format, renderer, target]) {
  return {
    resource_id: `resource-${renderer}`,
    ref_id: `resource-${renderer}`,
    group_id: `group-${renderer}`,
    parent_resource_id: null,
    resource_key: 'primary',
    relation: 'primary',
    kind: target === 'visualization' ? 'visual' : (target === 'board' ? 'artifact' : 'file'),
    role: 'output',
    label: `${name}.${format}`,
    format,
    media_type: renderer === 'chart' ? 'application/json' : 'application/octet-stream',
    renderer,
    capabilities: ['preview', 'download'],
    actions: {},
    version: 1,
    status: 'active',
    content_url: `/api/sessions/e2e/resources/resource-${renderer}/content`,
    download_url: `/api/sessions/e2e/resources/resource-${renderer}/content?disposition=attachment`,
    size_bytes: 7,
    created_at: '2026-08-02T00:00:00Z',
    updated_at: '2026-08-02T00:00:00Z'
  }
}

async function mockApplication(page, fixture) {
  const resource = resourceFixture(fixture)
  const handler = async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/auth/runtime-config')) {
      return route.fulfill({ json: {
        authMode: 'mock', sysCode: 'SUYUAN',
        mockUser: { id: 'e2e', userName: 'e2e', name: 'E2E', roleCodes: ['SUYUAN_ADMIN'], isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN' }
      } })
    }
    if (url.pathname.endsWith(`/resources/${resource.resource_id}/content`)) {
      const bodies = {
        markdown: '# restored markdown', chart: '{"type":"bar","data":[]}',
        board: '<mxfile><diagram id="e2e" /></mxfile>', html: '<h1>restored html</h1>'
      }
      return route.fulfill({
        status: 200,
        contentType: resource.renderer === 'chart' ? 'application/json' : 'text/plain',
        body: bodies[resource.renderer] || 'fixture'
      })
    }
    if (/\/sessions\/e2e\/resources$/.test(url.pathname)) {
      return route.fulfill({ json: { session_id: 'e2e', resource_version: 1, resources: [resource], total: 1, next_cursor: null } })
    }
    if (/\/sessions\/e2e\/restore$/.test(url.pathname)) {
      return route.fulfill({ json: { session: {
        session_id: 'e2e', source: 'web', mode: 'assistant', conversation_history: [],
        resource_version: 1, resource_counts: { total: 1, documents: 0, visualizations: 0, boards: 0, files: 1 }
      } } })
    }
    if (/\/sessions\/?$/.test(url.pathname)) {
      return route.fulfill({ json: { sessions: [], stats: {} } })
    }
    return route.fulfill({ json: { tasks: [], sessions: [], items: [], data: [] } })
  }
  await page.route('**/api/suyuan/**', handler)
  await page.route('**/api/sessions/**', handler)
  return resource
}

for (const fixture of fixtures) {
  test(`${fixture[0]} resource opens through the catalog and survives restore`, async ({ page }) => {
    const resource = await mockApplication(page, fixture)
    await page.goto('/session/e2e')

    await expect(page.getByRole('button', { name: /文件产物/ })).toBeVisible()
    await page.getByRole('button', { name: /文件产物/ }).click()
    await page.getByRole('button', { name: new RegExp(resource.label) }).click()
    await expect(page.locator('.tab-btn.active')).toContainText(tabLabel[fixture[3]])
    await expect(page.locator(fixture[4])).toBeVisible()

    await page.reload()
    await expect(page.locator('.tab-btn.active')).toContainText(tabLabel[fixture[3]])
    await expect(page.locator(fixture[4])).toBeVisible()
  })
}
