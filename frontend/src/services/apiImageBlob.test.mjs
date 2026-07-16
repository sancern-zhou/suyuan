import test from 'node:test'
import assert from 'node:assert/strict'

import {
  apiImagePath,
  createLatestImageObjectUrlLoader,
  loadApiImageObjectUrl,
  objectUrlToDataUrl
} from './apiImageBlob.js'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

test('apiImagePath accepts API URLs and legacy placeholders', () => {
  assert.equal(apiImagePath('/api/image/chart_1'), '/api/image/chart_1')
  assert.equal(apiImagePath('[IMAGE:chart_1]'), '/api/image/chart_1')
  assert.equal(apiImagePath('https://example.test/image.png'), null)
})

test('loadApiImageObjectUrl fetches image bytes through the supplied authenticated client', async () => {
  const calls = []
  const blob = new Blob(['png'], { type: 'image/png' })
  const fetchImage = async path => {
    calls.push(path)
    return new Response(blob, { headers: { 'Content-Type': 'image/png' } })
  }
  const created = []

  const url = await loadApiImageObjectUrl('/api/image/chart_1', {
    fetchImage,
    createObjectURL(value) {
      created.push(value)
      return 'blob:chart-1'
    }
  })

  assert.equal(url, 'blob:chart-1')
  assert.deepEqual(calls, ['/api/image/chart_1'])
  assert.equal(created.length, 1)
  assert.equal(created[0].type, 'image/png')
})

test('loadApiImageObjectUrl rejects HTTP failures before creating an Object URL', async () => {
  await assert.rejects(
    () => loadApiImageObjectUrl('/api/image/missing', {
      fetchImage: async () => new Response('missing', { status: 404 }),
      createObjectURL() {
        throw new Error('must not create')
      }
    }),
    /HTTP 404/
  )
})

test('loadApiImageObjectUrl rejects non-image responses before creating an Object URL', async () => {
  await assert.rejects(
    () => loadApiImageObjectUrl('/api/image/not-image', {
      fetchImage: async () => new Response('<html>', {
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
  const loader = createLatestImageObjectUrlLoader({
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
  const loader = createLatestImageObjectUrlLoader({
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
  const loader = createLatestImageObjectUrlLoader({
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
