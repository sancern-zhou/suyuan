import test from 'node:test'
import assert from 'node:assert/strict'
import { computed, ref } from 'vue'

import { completeUploadedAttachment } from './inputBoxAttachments.js'

test('upload completion invalidates selected file refs through the reactive array proxy', () => {
  const attachments = ref([])
  const pendingAttachment = {
    name: 'architecture.png',
    uploading: true,
    resourceRefId: null
  }
  attachments.value.push(pendingAttachment)

  const selectedFileRefs = computed(() => (
    attachments.value.filter(item => item.resourceRefId)
  ))
  assert.equal(selectedFileRefs.value.length, 0)

  completeUploadedAttachment(attachments.value, pendingAttachment, {
    file_id: 'file-1',
    resource_ref: { ref_id: 'resource-1' },
    url: '/api/files/file-1',
    mime_type: 'image/png',
    file_size: 123
  })

  assert.equal(selectedFileRefs.value.length, 1)
  assert.equal(selectedFileRefs.value[0].resourceRefId, 'resource-1')
  assert.equal(selectedFileRefs.value[0].uploading, false)
})

test('upload completion exposes a removed pending attachment as an error', () => {
  assert.throws(
    () => completeUploadedAttachment([], { name: 'removed.png' }, {
      file_id: 'file-1',
      resource_ref: { ref_id: 'resource-1' }
    }),
    /待更新附件不存在/
  )
})
