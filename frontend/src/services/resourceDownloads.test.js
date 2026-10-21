import assert from 'node:assert/strict'
import test from 'node:test'

import { downloadFileName, downloadResource } from './resourceDownloads.js'

const resource = {
  resource_id: 'ppt',
  label: 'presentation',
  format: 'pptx',
  download_url: '/api/suyuan/sessions/s/resources/ppt/content?disposition=attachment'
}

test('downloads a resource through authenticated fetch and a data URL', async () => {
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
  const dataUrl = 'data:application/vnd.openxmlformats-officedocument.presentationml.presentation;base64,cHB0eA=='
  const fileReader = class {
    readAsDataURL(value) {
      calls.push(['read', value])
      this.result = dataUrl
      this.onload()
    }
  }
  const blob = new Blob(['pptx'], { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' })

  await downloadResource(resource, {
    fetchImpl: async url => {
      calls.push(['fetch', url])
      return { ok: true, blob: async () => blob }
    },
    documentRef,
    fileReader,
    schedule: callback => callback()
  })

  assert.equal(link.href, dataUrl)
  assert.equal(link.download, 'presentation.pptx')
  assert.deepEqual(calls, [
    ['fetch', resource.download_url],
    ['read', blob],
    ['append', link],
    'click',
    'remove'
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

test('propagates DOM failures after reading the resource', async () => {
  const fileReader = class {
    readAsDataURL() {
      this.result = 'data:text/plain;base64,cHB0eA=='
      this.onload()
    }
  }
  await assert.rejects(
    downloadResource(resource, {
      fetchImpl: async () => ({ ok: true, blob: async () => new Blob(['pptx']) }),
      documentRef: { createElement: () => { throw new Error('dom unavailable') } },
      fileReader,
      schedule: () => assert.fail('must not schedule cleanup')
    }),
    /dom unavailable/
  )
})

test('cleans up exactly once when scheduling cleanup fails', async () => {
  let removals = 0
  const link = { click: () => {}, remove: () => { removals += 1 } }
  const fileReader = class {
    readAsDataURL() {
      this.result = 'data:text/plain;base64,cHB0eA=='
      this.onload()
    }
  }
  await assert.rejects(
    downloadResource(resource, {
      fetchImpl: async () => ({ ok: true, blob: async () => new Blob(['pptx']) }),
      documentRef: {
        createElement: () => link,
        body: { appendChild: () => {} }
      },
      fileReader,
      schedule: () => { throw new Error('scheduler unavailable') }
    }),
    /scheduler unavailable/
  )
  assert.equal(removals, 1)
})

test('normalizes the resource filename extension', () => {
  assert.equal(downloadFileName(resource), 'presentation.pptx')
  assert.equal(downloadFileName({ label: 'deck.pptx', format: 'pptx' }), 'deck.pptx')
})
