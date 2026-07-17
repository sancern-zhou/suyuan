import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createMarkdownApiImageHydrator,
  deferredApiImageAttributes,
  escapeRawHtmlImageTags,
  renderDeferredApiImage
} from './markdownApiImages.js'

function deferred() {
  let resolve
  const promise = new Promise(resolvePromise => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function fakeImage(source) {
  const attributes = new Map([['data-api-image-src', source]])
  return {
    getAttribute(name) {
      return attributes.get(name) || null
    },
    setAttribute(name, value) {
      attributes.set(name, value)
    },
    removeAttribute(name) {
      attributes.delete(name)
    }
  }
}

function fakeRoot(images) {
  return {
    querySelectorAll(selector) {
      assert.equal(selector, '[data-api-image-src]')
      return images
    },
    contains(image) {
      return images.includes(image)
    }
  }
}

test('deferredApiImageAttributes defers every same-origin API image', () => {
  assert.deepEqual(deferredApiImageAttributes('/api/image/chart_1'), {
    'data-api-image-src': '/api/image/chart_1'
  })
  assert.deepEqual(
    deferredApiImageAttributes('/api/html-artifacts/atmos_monitor_arch/assets/diagram.drawio.svg'),
    {
      'data-api-image-src': '/api/html-artifacts/atmos_monitor_arch/assets/diagram.drawio.svg'
    }
  )
  assert.deepEqual(deferredApiImageAttributes('/api/reports/report-1/assets/chart.png'), {
    'data-api-image-src': '/api/reports/report-1/assets/chart.png'
  })
  assert.deepEqual(deferredApiImageAttributes('[IMAGE:chart_1]'), {
    'data-api-image-src': '/api/image/chart_1'
  })
  assert.equal(deferredApiImageAttributes('https://example.test/chart.png'), null)
  assert.equal(deferredApiImageAttributes('assets/chart.png'), null)
})

test('Markdown hydrator loads every deferred image and owns the resulting URLs', async () => {
  const first = fakeImage('/api/image/one')
  const second = fakeImage('/api/image/two')
  const revoked = []
  const hydrator = createMarkdownApiImageHydrator({
    loadObjectUrl: async source => `blob:${source.split('/').pop()}`,
    revokeObjectURL: url => revoked.push(url)
  })

  await hydrator.hydrate(fakeRoot([first, second]))

  assert.equal(first.getAttribute('src'), 'blob:one')
  assert.equal(second.getAttribute('src'), 'blob:two')
  assert.equal(first.getAttribute('data-api-image-src'), null)
  assert.equal(second.getAttribute('data-api-image-src'), null)

  hydrator.clear()
  assert.deepEqual(revoked.sort(), ['blob:one', 'blob:two'])
})

test('Markdown hydrator reports a failure without exposing the raw API URL as src', async () => {
  const image = fakeImage('/api/image/broken')
  const errors = []
  const hydrator = createMarkdownApiImageHydrator({
    loadObjectUrl: async () => {
      throw new Error('broken image')
    },
    onError: (error, source) => errors.push([error.message, source])
  })

  await hydrator.hydrate(fakeRoot([image]))

  assert.equal(image.getAttribute('src'), null)
  assert.equal(image.getAttribute('data-api-image-src'), '/api/image/broken')
  assert.deepEqual(errors, [['broken image', '/api/image/broken']])
})

test('Markdown hydrator revokes stale results from an obsolete render', async () => {
  const pending = deferred()
  const oldImage = fakeImage('/api/image/old')
  const newImage = fakeImage('/api/image/new')
  const revoked = []
  const hydrator = createMarkdownApiImageHydrator({
    loadObjectUrl: source => source.endsWith('/old')
      ? pending.promise
      : Promise.resolve('blob:new'),
    revokeObjectURL: url => revoked.push(url)
  })

  const oldHydration = hydrator.hydrate(fakeRoot([oldImage]))
  await hydrator.hydrate(fakeRoot([newImage]))
  pending.resolve('blob:old')
  await oldHydration

  assert.equal(oldImage.getAttribute('src'), null)
  assert.equal(newImage.getAttribute('src'), 'blob:new')
  assert.deepEqual(revoked, ['blob:old'])

  hydrator.clear()
  assert.deepEqual(revoked, ['blob:old', 'blob:new'])
})

test('renderDeferredApiImage escapes attributes and never emits a raw API src', () => {
  const html = renderDeferredApiImage({
    src: '/api/image/chart_1?label="unsafe"',
    alt: '<浓度趋势>',
    cssClass: 'md-external-image'
  })

  assert.match(html, /data-api-image-src="\/api\/image\/chart_1\?label=&quot;unsafe&quot;"/)
  assert.match(html, /alt="&lt;浓度趋势&gt;"/)
  assert.doesNotMatch(html, /\s+src="\/api\/image\//)
  assert.match(html, /<p class="md-image-caption">&lt;浓度趋势&gt;<\/p>/)
})

test('renderDeferredApiImage handles HTML artifact media without endpoint-specific logic', () => {
  const source = '/api/html-artifacts/atmos_monitor_arch/assets/diagram.drawio.svg'
  const html = renderDeferredApiImage({ src: source, alt: '架构图' })

  assert.match(html, new RegExp(`data-api-image-src="${source}"`))
  assert.doesNotMatch(html, new RegExp(`\\s+src="${source}"`))
})

test('escapeRawHtmlImageTags prevents raw HTML images from issuing browser requests', () => {
  const html = [
    '<p><img src="/api/image/raw_one" alt="one"></p>',
    '<IMG src="&sol;api&sol;image&sol;named">',
    '<img src=" /api/image/space">',
    '<img src="\\api\\image\\slash">',
    '<img src="https://example.test/public.png" alt="public">'
  ].join('')

  const escaped = escapeRawHtmlImageTags(html)

  assert.doesNotMatch(escaped, /<img\b/i)
  assert.equal((escaped.match(/&lt;img/gi) || []).length, 5)
})
