import assert from 'node:assert/strict'
import test from 'node:test'

import {
  attachmentResourceId,
  isImageAttachmentResource,
  resolveMessageAttachmentResource
} from './messageAttachmentPreview.js'

const attachment = {
  resource_id: 'attachment-1',
  role: 'attachment',
  status: 'active',
  renderer: 'pdf'
}

test('resolves only active message attachments from the active session catalog', async () => {
  const state = { resources: [attachment] }
  const store = {
    activeSessionId: 'session-1',
    sessionState: () => state,
    loadCatalog: async () => { throw new Error('catalog should already be loaded') }
  }

  assert.equal(attachmentResourceId({ resource_ref: { ref_id: 'attachment-1' } }), 'attachment-1')
  assert.equal(
    await resolveMessageAttachmentResource(store, 'session-1', { resource_id: 'attachment-1' }),
    attachment
  )
})

test('loads a missing catalog entry once and rejects internal source resources', async () => {
  const state = { resources: [] }
  let loads = 0
  const store = {
    activeSessionId: 'session-1',
    sessionState: () => state,
    loadCatalog: async () => {
      loads += 1
      state.resources = [{ ...attachment, resource_id: 'source-1', role: 'source' }]
    }
  }

  await assert.rejects(
    resolveMessageAttachmentResource(store, 'session-1', { resource_id: 'source-1' }),
    /附件资源不可用/
  )
  assert.equal(loads, 1)
})

test('recognizes unified image resources without relying on message attachment type', () => {
  assert.equal(isImageAttachmentResource({ renderer: 'image' }), true)
  assert.equal(isImageAttachmentResource({ media_type: 'image/png' }), true)
  assert.equal(isImageAttachmentResource({ renderer: 'pdf', media_type: 'application/pdf' }), false)
})
