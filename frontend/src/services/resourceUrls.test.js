import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { browserResourceUrl } from './resourceUrls.js'

test('server root-absolute resource URLs inherit the deployed gateway base', () => {
  const contentUrl = '/api/suyuan/sessions/s1/resources/r1/content?preview_ticket=abc'
  assert.equal(
    browserResourceUrl(contentUrl, './api/suyuan'),
    './api/suyuan/sessions/s1/resources/r1/content?preview_ticket=abc'
  )
  assert.equal(browserResourceUrl(contentUrl, '/api/suyuan'), contentUrl)
})

test('unprefixed internal API URLs receive the gateway prefix', () => {
  assert.equal(
    browserResourceUrl('/api/sessions/s1/resources/r1/content', './api/suyuan'),
    './api/suyuan/sessions/s1/resources/r1/content'
  )
})

test('relative and non-string values pass through untouched', () => {
  assert.equal(browserResourceUrl('assets/report.html', './api/suyuan'), 'assets/report.html')
  assert.equal(browserResourceUrl('', './api/suyuan'), '')
  assert.equal(browserResourceUrl(undefined, './api/suyuan'), undefined)
})


const browserNavigationSurfaces = [
  'components/resources/renderers/HtmlResourceRenderer.vue',
  'components/resources/renderers/PdfResourceRenderer.vue',
  'components/resources/renderers/ImageResourceRenderer.vue',
  'components/resources/renderers/PresentationResourceRenderer.vue',
  'components/resources/renderers/FileDetailRenderer.vue',
  'components/InlineHtmlCard.vue',
  'components/reactAnalysis/MainLayout.vue'
]

test('browser-navigation surfaces normalise resource URLs through the gateway base', async () => {
  for (const relative of browserNavigationSurfaces) {
    const source = await readFile(new URL(`../${relative}`, import.meta.url), 'utf8')
    assert.match(source, /browserResourceUrl/, `${relative} must not hand root-absolute URLs to the browser`)
    assert.doesNotMatch(source, /:src="(?:resource|page)\.content_url"/, `${relative} binds a raw content_url into src`)
  }
})
