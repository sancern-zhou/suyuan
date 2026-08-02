import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const rendererNames = [
  'PdfResourceRenderer', 'HtmlResourceRenderer', 'MarkdownResourceRenderer',
  'SpreadsheetResourceRenderer', 'PresentationResourceRenderer', 'ImageResourceRenderer',
  'ChartResourceRenderer', 'BoardResourceRenderer', 'FileDetailRenderer'
]

test('preview host uses the resource store and opaque content boundary', async () => {
  const source = await readFile(new URL('./ResourcePreviewHost.vue', import.meta.url), 'utf8')
  assert.match(source, /useSessionResourceStore/)
  assert.match(source, /rendererKey/)
  assert.match(source, /content-url/)
  assert.match(source, /explicitAttachment/)
  assert.match(source, /preferredPreview\(group\.value\) \|\| explicitAttachment\.value/)
  assert.match(source, /:floating="target === 'document' && resource\.renderer !== 'spreadsheet'"/)
  assert.match(source, /\.preview-layout \{ position: relative;/)
  assert.doesNotMatch(source, /file_path|pdf_id|html_id|\/api\/file\//)
})

test('document preview actions expose an overlay menu without reserving layout space', async () => {
  const source = await readFile(new URL('./ResourcePreviewActions.vue', import.meta.url), 'utf8')
  assert.match(source, /class="download-trigger"/)
  assert.match(source, /aria-haspopup="menu"/)
  assert.match(source, /\{ floating \}/)
  assert.match(source, /position: absolute/)
  assert.match(source, /handleDocumentPointerDown/)
  assert.match(source, /event\.key === 'Escape'/)
})

test('renderers accept only resource, group and contentUrl boundary props', async () => {
  for (const name of rendererNames) {
    const source = await readFile(new URL(`./renderers/${name}.vue`, import.meta.url), 'utf8')
    assert.match(source, /defineProps/)
    assert.match(source, /resource/)
    assert.match(source, /group/)
    assert.match(source, /contentUrl/)
    assert.doesNotMatch(source, /api\/session|reactStore|file_path|pdf_id|html_id|\/api\/file\//)
  }
})
