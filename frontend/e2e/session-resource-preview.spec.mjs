import { expect, test } from 'playwright/test'
import * as XLSX from 'xlsx'

const fixtures = [
  ['DOCX/PDF', 'pdf', 'pdf', 'document', '.resource-preview-host iframe'],
  ['HTML', 'html', 'html', 'document', '.resource-preview-host iframe[sandbox]'],
  ['Markdown', 'md', 'markdown', 'document', '.resource-preview-host .scroll'],
  ['Spreadsheet', 'xlsx', 'spreadsheet', 'document', '.resource-preview-host .excel-editor'],
  ['Presentation', 'pptx', 'presentation', 'document', '.resource-preview-host .slides'],
  ['Image', 'png', 'image', 'visualization', '.visualization-gallery .image'],
  ['Chart', 'json', 'chart', 'visualization', '.visualization-gallery .chart'],
  ['Board', 'drawio', 'board', 'board', '.resource-preview-host .board']
]

const tabLabel = { document: '文档', visualization: '可视化', board: '画板' }

function resourceFixture([name, format, renderer, target]) {
  const resource = {
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
  if (renderer === 'spreadsheet') {
    resource.capabilities.push('edit')
    resource.actions.save = `/api/sessions/e2e/resources/resource-${renderer}/save`
  }
  return resource
}

function spreadsheetFixtureBytes() {
  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([['Original', 1]]), '数据')
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([['Second sheet']]), '说明')
  return XLSX.write(workbook, { type: 'buffer', bookType: 'xlsx' })
}

const imageFixtureBytes = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64'
)

async function mockApplication(page, fixture, {
  attachmentType = null,
  officePreview = false,
  extraFixtures = [],
  extraResources = [],
  failCatalogRefreshAfterSave = false
} = {}) {
  const resource = resourceFixture(fixture)
  if (attachmentType) resource.role = 'attachment'
  const resources = [resource]
  let resourceVersion = 1
  let spreadsheetSaved = false
  resources.push(...extraFixtures.map(resourceFixture))
  resources.push(...extraResources)
  if (officePreview) {
    resource.label = 'Office attachment.docx'
    resource.format = 'docx'
    resource.renderer = 'file'
    resource.capabilities = ['download']
    resources.push({
      ...resourceFixture(fixtures[0]),
      resource_id: 'resource-office-pdf-preview',
      ref_id: 'resource-office-pdf-preview',
      group_id: resource.group_id,
      parent_resource_id: resource.resource_id,
      resource_key: 'preview:pdf',
      relation: 'preview',
      role: 'attachment',
      label: 'Office attachment.pdf',
      capabilities: ['preview'],
      content_url: '/api/sessions/e2e/resources/resource-office-pdf-preview/content',
      download_url: null
    })
  }
  const handler = async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/auth/runtime-config')) {
      return route.fulfill({ json: {
        authMode: 'mock', sysCode: 'SUYUAN',
        mockUser: { id: 'e2e', userName: 'e2e', name: 'E2E', roleCodes: ['SUYUAN_ADMIN'], isAdmin: true, authSource: 'mock', sysCode: 'SUYUAN' }
      } })
    }
    const contentResource = resources.find(item => url.pathname.endsWith(`/resources/${item.resource_id}/content`))
    if (contentResource) {
      const bodies = {
        markdown: '# restored markdown', chart: '{"type":"bar","data":[]}',
        board: '<mxfile><diagram id="e2e" /></mxfile>', html: '<h1>restored html</h1>'
      }
      return route.fulfill({
        status: 200,
        contentType: contentResource.renderer === 'chart'
          ? 'application/json'
          : (contentResource.renderer === 'image'
              ? 'image/png'
          : (contentResource.renderer === 'spreadsheet'
              ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
              : 'text/plain')),
        headers: url.searchParams.get('disposition') === 'attachment'
          ? { 'Content-Disposition': `attachment; filename="${contentResource.label}"` }
          : {},
        body: contentResource.renderer === 'spreadsheet'
          ? spreadsheetFixtureBytes()
          : (contentResource.renderer === 'image'
              ? imageFixtureBytes
          : (bodies[contentResource.renderer] || 'fixture')
            )
      })
    }
    if (url.pathname.endsWith('/resources/resource-spreadsheet/save')) {
      const currentIndex = resources.findIndex(item => item.resource_id === 'resource-spreadsheet')
      const current = resources[currentIndex]
      const next = {
        ...current,
        resource_id: 'resource-spreadsheet-v2',
        ref_id: 'resource-spreadsheet-v2',
        version: 2,
        content_url: '/api/sessions/e2e/resources/resource-spreadsheet-v2/content',
        download_url: '/api/sessions/e2e/resources/resource-spreadsheet-v2/content?disposition=attachment',
        actions: { save: '/api/sessions/e2e/resources/resource-spreadsheet-v2/save' }
      }
      resources.splice(currentIndex, 1, next)
      resourceVersion = 2
      spreadsheetSaved = true
      return route.fulfill({ json: {
        success: true,
        resource_version: 2,
        changed_resource_ids: [next.resource_id]
      } })
    }
    if (url.pathname.startsWith('/api/upload/')) {
      return route.fulfill({ status: 200, contentType: 'image/png', body: 'fixture' })
    }
    if (/\/sessions\/e2e\/resources$/.test(url.pathname)) {
      if (failCatalogRefreshAfterSave && spreadsheetSaved) {
        return route.fulfill({ status: 503, body: 'catalog unavailable' })
      }
      return route.fulfill({ json: { session_id: 'e2e', resource_version: resourceVersion, resources, total: resources.length, next_cursor: null } })
    }
    if (/\/sessions\/e2e\/restore$/.test(url.pathname)) {
      return route.fulfill({ json: { session: {
        session_id: 'e2e', source: 'web', mode: 'assistant', conversation_history: attachmentType ? [{
          id: 'message-attachment', role: 'user', type: 'user', content: '查看附件',
          attachments: [{
            resource_id: resource.resource_id,
            name: resource.label,
            type: attachmentType,
            mime_type: resource.media_type,
            url: '/api/upload/legacy-not-used-for-preview'
          }]
        }] : [],
        resource_version: 1, resource_counts: { total: 1, documents: 0, visualizations: 0, boards: 0, files: 1 }
      } } })
    }
    if (/\/sessions\/?$/.test(url.pathname)) {
      return route.fulfill({ json: { sessions: [], stats: {} } })
    }
    return route.fulfill({ json: { tasks: [], sessions: [], items: [], data: [] } })
  }
  await page.route('**/api/auth/**', handler)
  await page.route('**/api/suyuan/**', handler)
  await page.route('**/api/sessions/**', handler)
  await page.route('**/api/upload/**', handler)
  return resource
}

test('message document attachment opens explicitly without entering file products', async ({ page }) => {
  await mockApplication(page, fixtures[0], { attachmentType: 'file' })
  await page.goto('/session/e2e')

  await expect(page.locator('.attachment-file')).toBeVisible()
  await page.locator('.attachment-file').click()
  await expect(page.locator('.tab-btn.active')).toContainText('文档')
  await expect(page.locator('.resource-preview-host iframe')).toBeVisible()
  await expect(page.locator('.product-list .product')).toHaveCount(0)

  await page.reload()
  await expect(page.locator('.resource-preview-host')).toHaveCount(0)
  await page.locator('.attachment-file').click()
  await expect(page.locator('.resource-preview-host iframe')).toBeVisible()
})

test('document toolbar identifies the file and expands its download menu', async ({ page }) => {
  await mockApplication(page, fixtures[0])
  await page.goto('/session/e2e')

  await page.getByRole('tab', { name: /文件产物/ }).click()
  await page.getByRole('button', { name: /DOCX\/PDF\.pdf/ }).click()

  const actions = page.locator('.resource-preview-host .resource-actions.compact')
  await expect(page.locator('.document-picker select')).toHaveValue('group-pdf')
  await expect(actions.getByRole('button', { name: '下载' })).toBeVisible()

  await actions.getByRole('button', { name: '下载' }).click()
  await expect(actions.getByRole('menu')).toBeVisible()
  await expect(actions.getByRole('menuitem', { name: '下载原始 PDF' })).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(actions.getByRole('menu')).toHaveCount(0)
})

test('message image attachment keeps the image modal while resolving unified content', async ({ page }) => {
  await mockApplication(page, fixtures[5], { attachmentType: 'image' })
  await page.goto('/session/e2e')

  await page.locator('.attachment-image').click()
  await expect(page.locator('.image-preview-modal')).toBeVisible()
  await expect(page.locator('.image-preview-modal .preview-filename')).toContainText('Image.png')
})

test('message DOCX attachment opens its unified PDF preview derivative', async ({ page }) => {
  await mockApplication(page, fixtures[0], { attachmentType: 'file', officePreview: true })
  await page.goto('/session/e2e')

  await page.locator('.attachment-file').click()
  await expect(page.locator('.tab-btn.active')).toContainText('文档')
  await expect(page.locator('.resource-preview-host iframe')).toHaveAttribute(
    'src',
    /resource-office-pdf-preview/
  )
})

test('explicit document selection does not leak into the visualization tab', async ({ page }) => {
  await mockApplication(page, fixtures[0], {
    attachmentType: 'file',
    extraFixtures: [fixtures[6]]
  })
  await page.goto('/session/e2e')

  await page.locator('.attachment-file').click()
  await expect(page.locator('.resource-preview-host iframe')).toBeVisible()
  await page.getByRole('tab', { name: /可视化/ }).click()
  await expect(page.locator('.visualization-gallery .chart')).toBeVisible()
  await expect(page.locator('.resource-preview-host iframe')).toHaveCount(0)
})

test('file product open and download actions do not overlap', async ({ page }) => {
  await mockApplication(page, fixtures[0])
  await page.goto('/session/e2e')
  await page.getByRole('tab', { name: /文件产物/ }).click()

  const openBox = await page.locator('.product .open-label').boundingBox()
  const downloadBox = await page.locator('.product .download').boundingBox()
  const overlaps = openBox.x < downloadBox.x + downloadBox.width
    && openBox.x + openBox.width > downloadBox.x
    && openBox.y < downloadBox.y + downloadBox.height
    && openBox.y + openBox.height > downloadBox.y
  expect(overlaps).toBe(false)
})

test('preview original download is a native browser download link', async ({ page }) => {
  await mockApplication(page, fixtures[3])
  await page.goto('/session/e2e')
  await page.getByRole('tab', { name: /文件产物/ }).click()
  await page.getByRole('button', { name: /Spreadsheet.xlsx/ }).click()

  const actions = page.locator('.resource-actions.compact')
  await expect(actions.getByRole('button', { name: '下载' })).toBeVisible()
  await actions.getByRole('button', { name: '下载' }).click()
  const downloadLink = actions.getByRole('menuitem', { name: '下载原始 Excel' })
  await expect(downloadLink).toHaveText('下载原始 Excel')
  const download = page.waitForEvent('download')
  await downloadLink.click()
  expect((await download).suggestedFilename()).toBe('Spreadsheet.xlsx')
})

test('file product actions stay fixed when the product has an HTML rendition', async ({ page }) => {
  const primary = {
    ...resourceFixture(fixtures[2]),
    resource_id: 'resource-qmd',
    ref_id: 'resource-qmd',
    group_id: 'group-qmd',
    resource_key: 'primary:qmd',
    role: 'report',
    label: '正式报告.qmd',
    format: 'qmd',
    capabilities: ['preview', 'download', 'render'],
    actions: { render: '/api/sessions/e2e/resources/resource-qmd/render' }
  }
  const html = {
    ...resourceFixture(fixtures[1]),
    resource_id: 'resource-qmd-html',
    ref_id: 'resource-qmd-html',
    group_id: primary.group_id,
    parent_resource_id: primary.resource_id,
    resource_key: 'rendition:html',
    relation: 'rendition',
    role: 'report',
    label: '正式报告.html'
  }
  await mockApplication(page, fixtures[6], { extraResources: [primary, html] })
  await page.goto('/session/e2e')
  await page.getByRole('tab', { name: /文件产物/ }).click()

  const product = page.locator('.product').filter({ hasText: '正式报告.qmd' })
  const actions = product.locator('.product-actions')
  await expect(actions).toBeVisible()
  await expect(actions.getByText('打开', { exact: true })).toBeVisible()
  await expect(actions.getByText('下载', { exact: true })).toBeVisible()

  await actions.getByText('打开', { exact: true }).click()
  const previewActions = page.locator('.resource-preview-host .resource-actions.compact')
  await previewActions.getByRole('button', { name: '下载' }).click()
  await expect(previewActions.getByText('导出报告', { exact: true })).toHaveCount(0)
  await expect(previewActions.getByRole('menuitem', { name: '导出 HTML' })).toBeVisible()
  await expect(previewActions.getByRole('menuitem', { name: '导出 Word' })).toBeVisible()
})

test('spreadsheet preview switches sheets, edits a cell, and refreshes after save', async ({ page }) => {
  await mockApplication(page, fixtures[3])
  await page.goto('/session/e2e')
  await page.getByRole('tab', { name: /文件产物/ }).click()
  await page.getByRole('button', { name: /Spreadsheet.xlsx/ }).click()

  await expect(page.getByRole('tab', { name: '数据' })).toBeVisible()
  await page.getByRole('tab', { name: '说明' }).click()
  await expect(page.locator('.cell-input').first()).toHaveValue('Second sheet')
  await page.getByRole('tab', { name: '数据' }).click()
  await page.locator('.cell-input').first().fill('Edited')
  await expect(page.locator('.cell-input').first()).toHaveValue('Edited')
  await page.getByRole('button', { name: '保存' }).click()

  await expect(page.locator('.excel-status')).toContainText('已保存')
  const actions = page.locator('.resource-actions.compact')
  await actions.getByRole('button', { name: '下载' }).click()
  await expect(actions.getByRole('menuitem', { name: '下载原始 Excel' })).toHaveAttribute(
    'href',
    /resource-spreadsheet-v2/
  )
})

test('visualization gallery automatically shows every chart and image', async ({ page }) => {
  await mockApplication(page, fixtures[6], { extraFixtures: [fixtures[5]] })
  await page.goto('/session/e2e')

  await page.getByRole('tab', { name: /可视化/ }).click()
  await expect(page.locator('.visualization-card')).toHaveCount(2)
  await expect(page.locator('.visualization-gallery .chart')).toBeVisible()
  await expect(page.locator('.visualization-gallery .image')).toBeVisible()
  await expect(page.locator('.gallery-heading')).toContainText('2 项')
})

test('a failed chart stays isolated and can retry without hiding other visuals', async ({ page }) => {
  await mockApplication(page, fixtures[6], { extraFixtures: [fixtures[5]] })
  let chartAttempts = 0
  await page.route('**/resources/resource-chart/content*', async route => {
    chartAttempts += 1
    await route.fulfill({ status: 503, body: 'chart unavailable' })
  })
  await page.goto('/session/e2e')

  const chartCard = page.locator('.visualization-card').filter({ hasText: 'Chart.json' })
  await expect(chartCard.locator('.error')).toContainText('HTTP 503')
  await expect(page.locator('.visualization-gallery .image img')).toBeVisible()
  await chartCard.getByRole('button', { name: '重试' }).click()
  await expect.poll(() => chartAttempts).toBeGreaterThanOrEqual(2)
  await expect(page.locator('.visualization-card')).toHaveCount(2)
})

test('spreadsheet keeps edited cells visible when post-save catalog refresh fails', async ({ page }) => {
  await mockApplication(page, fixtures[3], { failCatalogRefreshAfterSave: true })
  await page.goto('/session/e2e')
  await page.getByRole('tab', { name: /文件产物/ }).click()
  await page.getByRole('button', { name: /Spreadsheet.xlsx/ }).click()
  await page.locator('.cell-input').first().fill('Unsynced preview')
  await page.getByRole('button', { name: '保存' }).click()

  await expect(page.locator('.excel-status')).toContainText('catalog unavailable')
  await expect(page.locator('.cell-input').first()).toHaveValue('Unsynced preview')
})

test('spreadsheet unsaved edits block tab changes and panel closing', async ({ page }) => {
  await mockApplication(page, fixtures[3], { extraFixtures: [fixtures[6]] })
  await page.goto('/session/e2e')
  await page.getByRole('tab', { name: /文件产物/ }).click()
  await page.getByRole('button', { name: /Spreadsheet.xlsx/ }).click()
  await page.locator('.cell-input').first().fill('Keep this edit')
  await expect(page.locator('.dirty-state')).toHaveText('未保存')

  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('tab', { name: /可视化/ }).click()
  await expect(page.locator('.tab-btn.active')).toContainText('文档')
  await expect(page.locator('.cell-input').first()).toHaveValue('Keep this edit')

  page.once('dialog', dialog => dialog.dismiss())
  await page.locator('.viz-toggle-btn').click()
  await expect(page.locator('.resource-preview-host')).toBeVisible()
  await expect(page.locator('.cell-input').first()).toHaveValue('Keep this edit')
})

test('empty resource tabs are disabled', async ({ page }) => {
  await mockApplication(page, fixtures[0])
  await page.goto('/session/e2e')

  await expect(page.getByRole('tab', { name: /可视化/ })).toBeDisabled()
  await expect(page.getByRole('tab', { name: /溯源/ })).toBeDisabled()
  await expect(page.getByRole('tab', { name: /文档/ })).toBeEnabled()
})

for (const fixture of fixtures) {
  test(`${fixture[0]} resource opens through the catalog and survives restore`, async ({ page }) => {
    const resource = await mockApplication(page, fixture)
    await page.goto('/session/e2e')

    await expect(page.getByRole('tab', { name: /文件产物/ })).toBeVisible()
    await page.getByRole('tab', { name: /文件产物/ }).click()
    await page.getByRole('button', { name: new RegExp(resource.label) }).click()
    await expect(page.locator('.tab-btn.active')).toContainText(tabLabel[fixture[3]])
    await expect(page.locator(fixture[4])).toBeVisible()

    await page.reload()
    await expect(page.locator('.tab-btn.active')).toContainText(tabLabel[fixture[3]])
    await expect(page.locator(fixture[4])).toBeVisible()
  })
}
