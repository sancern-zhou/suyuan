import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createLatestMediaObjectUrlLoader,
  loadApiMediaObjectUrl,
  objectUrlToDataUrl,
  sameOriginApiMediaPath
} from './apiMediaBlob.js'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

test('sameOriginApiMediaPath accepts every same-origin API media path', () => {
  assert.equal(sameOriginApiMediaPath('/api/image/chart_1'), '/api/image/chart_1')
  assert.equal(
    sameOriginApiMediaPath('/api/html-artifacts/atmos_monitor_arch/assets/diagram.drawio.svg'),
    '/api/html-artifacts/atmos_monitor_arch/assets/diagram.drawio.svg'
  )
  assert.equal(
    sameOriginApiMediaPath('/api/reports/report-1/assets/chart.png?download=0'),
    '/api/reports/report-1/assets/chart.png?download=0'
  )
  assert.equal(sameOriginApiMediaPath('/api/signed-media/token-1'), '/api/signed-media/token-1')
})

test('sameOriginApiMediaPath preserves legacy placeholders at the compatibility boundary', () => {
  assert.equal(sameOriginApiMediaPath('[IMAGE:chart_1]'), '/api/image/chart_1')
})

test('sameOriginApiMediaPath rejects non-API and external sources', () => {
  assert.equal(sameOriginApiMediaPath('https://example.test/image.png'), null)
  assert.equal(sameOriginApiMediaPath('assets/chart.png'), null)
  assert.equal(sameOriginApiMediaPath('data:image/png;base64,abc'), null)
  assert.equal(sameOriginApiMediaPath('/api/'), null)
})

test('loadApiMediaObjectUrl fetches API media through the supplied authenticated client', async () => {
  const calls = []
  const blob = new Blob(['png'], { type: 'image/png' })
  const fetchMedia = async path => {
    calls.push(path)
    return new Response(blob, { headers: { 'Content-Type': 'image/png' } })
  }
  const created = []

  const url = await loadApiMediaObjectUrl('/api/html-artifacts/artifact-1/assets/diagram.svg', {
    fetchMedia,
    createObjectURL(value) {
      created.push(value)
      return 'blob:chart-1'
    }
  })

  assert.equal(url, 'blob:chart-1')
  assert.deepEqual(calls, ['/api/html-artifacts/artifact-1/assets/diagram.svg'])
  assert.equal(created.length, 1)
  assert.equal(created[0].type, 'image/png')
})

test('loadApiMediaObjectUrl preserves an encoded Unicode image ID for the gateway request', async () => {
  const source = '/api/image/%E8%AE%B8%E6%98%8C%E5%B8%827%E6%9C%88%E7%A9%BA%E6%B0%94%E8%B4%A8%E9%87%8F%E7%AD%89%E7%BA%A7%E5%88%86%E5%B8%83.png'
  const calls = []

  await loadApiMediaObjectUrl(source, {
    fetchMedia: async path => {
      calls.push(path)
      return new Response(new Blob(['png'], { type: 'image/png' }), {
        headers: { 'Content-Type': 'image/png' }
      })
    },
    createObjectURL: () => 'blob:unicode-chart'
  })

  assert.deepEqual(calls, [source])
})

test('loadApiMediaObjectUrl accepts legacy application image content types', async () => {
  const created = []

  const url = await loadApiMediaObjectUrl('/api/jiangsu/work-order-reviews/review-1/attachments/1/content', {
    fetchMedia: async () => new Response(new Blob(['png'], { type: 'application/png' }), {
      headers: { 'Content-Type': 'application/png' }
    }),
    createObjectURL(value) {
      created.push(value)
      return 'blob:normalised-png'
    }
  })

  assert.equal(url, 'blob:normalised-png')
  assert.equal(created.length, 1)
  assert.equal(created[0].type, 'image/png')
})

test('loadApiMediaObjectUrl rejects HTTP failures before creating an Object URL', async () => {
  await assert.rejects(
    () => loadApiMediaObjectUrl('/api/image/missing', {
      fetchMedia: async () => new Response('missing', { status: 404 }),
      createObjectURL() {
        throw new Error('must not create')
      }
    }),
    /HTTP 404/
  )
})

test('loadApiMediaObjectUrl rejects non-image responses before creating an Object URL', async () => {
  await assert.rejects(
    () => loadApiMediaObjectUrl('/api/image/not-image', {
      fetchMedia: async () => new Response('<html>', {
        headers: { 'Content-Type': 'text/html' }
      }),
      createObjectURL() {
        throw new Error('must not create')
      }
    }),
    /not an image/i
  )
})

test('latest image loader discards stale results and only settles the current request', async () => {
  const requests = new Map([
    ['first', deferred()],
    ['second', deferred()]
  ])
  const revoked = []
  const events = []
  const loader = createLatestMediaObjectUrlLoader({
    loadObjectUrl: source => requests.get(source).promise,
    revokeObjectURL: url => revoked.push(url)
  })

  const first = loader.start('first', {
    onSuccess: url => events.push(`success:${url}`),
    onSettled: () => events.push('settled:first')
  })
  const second = loader.start('second', {
    onSuccess: url => events.push(`success:${url}`),
    onSettled: () => events.push('settled:second')
  })

  requests.get('second').resolve('blob:second')
  await second
  requests.get('first').resolve('blob:first')
  await first

  assert.deepEqual(events, ['success:blob:second', 'settled:second'])
  assert.deepEqual(revoked, ['blob:first'])

  loader.clear()
  assert.deepEqual(revoked, ['blob:first', 'blob:second'])
})

test('latest image loader revokes a replaced URL and reports only current errors', async () => {
  const failure = deferred()
  const revoked = []
  const errors = []
  const settled = []
  const loader = createLatestMediaObjectUrlLoader({
    loadObjectUrl: source => {
      if (source === 'failure') return failure.promise
      return Promise.resolve(`blob:${source}`)
    },
    revokeObjectURL: url => revoked.push(url)
  })

  await loader.start('one')
  await loader.start('two')
  const staleFailure = loader.start('failure', {
    onError: error => errors.push(error.message),
    onSettled: () => settled.push('failure')
  })
  await loader.start('three', {
    onSettled: () => settled.push('three')
  })
  failure.reject(new Error('stale error'))
  await staleFailure

  assert.deepEqual(revoked, ['blob:one', 'blob:two'])
  assert.deepEqual(errors, [])
  assert.deepEqual(settled, ['three'])
})

test('clearing the latest image loader invalidates a pending direct-source request', async () => {
  const pending = deferred()
  const revoked = []
  const published = []
  const loader = createLatestMediaObjectUrlLoader({
    loadObjectUrl: () => pending.promise,
    revokeObjectURL: url => revoked.push(url)
  })

  const request = loader.start('/api/image/chart_1', {
    onSuccess: url => published.push(url)
  })
  loader.clear()
  pending.resolve('blob:stale')
  await request

  assert.deepEqual(published, [])
  assert.deepEqual(revoked, ['blob:stale'])
})

test('objectUrlToDataUrl preserves the screenshot capture data URL contract', async () => {
  const imageBlob = new Blob(['captured-image'], { type: 'image/png' })
  const calls = []

  const result = await objectUrlToDataUrl('blob:chart-1', {
    fetchObjectUrl: async url => {
      calls.push(url)
      return new Response(imageBlob)
    },
    readBlobAsDataUrl: async blob => `data:${blob.type};base64,${'a'.repeat(120)}`
  })

  assert.deepEqual(calls, ['blob:chart-1'])
  assert.match(result, /^data:image\/png;base64,/)
  assert.ok(result.length > 100)
})
