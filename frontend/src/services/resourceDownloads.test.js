import assert from 'node:assert/strict'
import test from 'node:test'

import { downloadFileName, downloadResource } from './resourceDownloads.js'

const resource = {
  resource_id: 'ppt',
  label: 'presentation',
  format: 'pptx',
  download_url: '/api/suyuan/sessions/s/resources/ppt/content?disposition=attachment'
}

test('downloads a resource through authenticated fetch and a temporary Blob URL', async () => {
  const calls = []
  const link = {
    click: () => calls.push('click'),
    remove: () => calls.push('remove')
  }
  const documentRef = {
    createElement: name => {
      assert.equal(name, 'a')
      return link
    },
    body: { appendChild: value => calls.push(['append', value]) }
  }
  const urlApi = {
    createObjectURL: value => {
      calls.push(['create', value])
      return 'blob:download'
    },
    revokeObjectURL: value => calls.push(['revoke', value])
  }
  const blob = new Blob(['pptx'], { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' })

  await downloadResource(resource, {
    fetchImpl: async url => {
      calls.push(['fetch', url])
      return { ok: true, blob: async () => blob }
    },
    documentRef,
    urlApi,
    schedule: callback => callback()
  })

  assert.equal(link.href, 'blob:download')
  assert.equal(link.download, 'presentation.pptx')
  assert.deepEqual(calls, [
    ['fetch', resource.download_url],
    ['create', blob],
    ['append', link],
    'click',
    'remove',
    ['revoke', 'blob:download']
  ])
})

test('reports an HTTP failure without creating a download', async () => {
  await assert.rejects(
    downloadResource(resource, {
      fetchImpl: async () => ({
        ok: false,
        status: 404,
        text: async () => 'resource_not_found'
      }),
      documentRef: { createElement: () => assert.fail('must not create an anchor') }
    }),
    /resource_not_found/
  )
})

test('revokes the Blob URL when DOM setup fails', async () => {
  const revoked = []
  await assert.rejects(
    downloadResource(resource, {
      fetchImpl: async () => ({ ok: true, blob: async () => new Blob(['pptx']) }),
      documentRef: { createElement: () => { throw new Error('dom unavailable') } },
      urlApi: {
        createObjectURL: () => 'blob:failed',
        revokeObjectURL: value => revoked.push(value)
      },
      schedule: () => assert.fail('must not schedule cleanup')
    }),
    /dom unavailable/
  )
  assert.deepEqual(revoked, ['blob:failed'])
})

test('cleans up exactly once when scheduling cleanup fails', async () => {
  let removals = 0
  const revoked = []
  const link = { click: () => {}, remove: () => { removals += 1 } }
  await assert.rejects(
    downloadResource(resource, {
      fetchImpl: async () => ({ ok: true, blob: async () => new Blob(['pptx']) }),
      documentRef: {
        createElement: () => link,
        body: { appendChild: () => {} }
      },
      urlApi: {
        createObjectURL: () => 'blob:schedule-failed',
        revokeObjectURL: value => revoked.push(value)
      },
      schedule: () => { throw new Error('scheduler unavailable') }
    }),
    /scheduler unavailable/
  )
  assert.equal(removals, 1)
  assert.deepEqual(revoked, ['blob:schedule-failed'])
})

test('normalizes the resource filename extension', () => {
  assert.equal(downloadFileName(resource), 'presentation.pptx')
  assert.equal(downloadFileName({ label: 'deck.pptx', format: 'pptx' }), 'deck.pptx')
})
