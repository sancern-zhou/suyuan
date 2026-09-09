import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { createMessageAttachmentMedia } from './messageAttachmentMedia.js'
import { loadApiMediaObjectUrl } from '../services/apiMediaBlob.js'


test('message attachment media loads protected API images as object URLs', async () => {
  const loaded = []
  const published = []
  const media = createMessageAttachmentMedia({
    loadObjectUrl: async source => {
      loaded.push(source)
      return 'blob:protected-image'
    },
    onChange: value => published.push(value)
  })

  await media.setSource('/api/upload/file-123')

  assert.deepEqual(loaded, ['/api/upload/file-123'])
  assert.equal(media.currentUrl(), 'blob:protected-image')
  assert.deepEqual(published, ['', 'blob:protected-image'])
})


test('JFIF media responses are normalized to JPEG object URLs', async () => {
  const requests = []
  const created = []
  const objectUrl = await loadApiMediaObjectUrl('/api/jiangsu/work-order-reviews/review-1/attachments/0/content', {
    fetchMedia: async source => {
      requests.push(source)
      return {
        ok: true,
        headers: { get: name => name === 'Content-Type' ? 'application/jfif' : '' },
        blob: async () => new Blob([new Uint8Array([0xff, 0xd8, 0xff])], { type: 'application/jfif' })
      }
    },
    createObjectURL: blob => {
      created.push(blob.type)
      return 'blob:jfif-image'
    }
  })

  assert.equal(objectUrl, 'blob:jfif-image')
  assert.deepEqual(requests, ['/api/jiangsu/work-order-reviews/review-1/attachments/0/content'])
  assert.deepEqual(created, ['image/jpeg'])
})


test('message attachment media revokes its object URL when cleared', async () => {
  const revoked = []
  const media = createMessageAttachmentMedia({
    loadObjectUrl: async () => 'blob:protected-image',
    revokeObjectURL: value => revoked.push(value)
  })

  await media.setSource('/api/upload/file-123')
  media.clear()

  assert.equal(media.currentUrl(), '')
  assert.deepEqual(revoked, ['blob:protected-image'])
})


test('message attachment media rejects non-API sources without issuing a request', async () => {
  let loadCount = 0
  const media = createMessageAttachmentMedia({
    loadObjectUrl: async () => {
      loadCount += 1
      return 'blob:unexpected'
    }
  })

  await media.setSource('https://example.test/untrusted.png')

  assert.equal(loadCount, 0)
  assert.equal(media.currentUrl(), '')
})


test('message attachment media preserves local image previews without an API request', async () => {
  let loadCount = 0
  const source = 'data:image/png;base64,abc'
  const media = createMessageAttachmentMedia({
    loadObjectUrl: async () => {
      loadCount += 1
      return 'blob:unexpected'
    }
  })

  await media.setSource(source)

  assert.equal(loadCount, 0)
  assert.equal(media.currentUrl(), source)
})


test('authenticated image forwards the native click event to modifier consumers', () => {
  const source = readFileSync(new URL('./AuthenticatedImage.vue', import.meta.url), 'utf8')

  assert.match(source, /@click="emit\('click', \$event\)"/)
})


test('authenticated image forwards native image load failures', () => {
  const source = readFileSync(new URL('./AuthenticatedImage.vue', import.meta.url), 'utf8')

  assert.match(source, /@error="emit\('error', \$event\)"/)
})
