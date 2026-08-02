export const attachmentResourceId = attachment => String(
  attachment?.resource_id
  || attachment?.resourceRefId
  || attachment?.resource_ref?.resource_id
  || attachment?.resource_ref?.ref_id
  || ''
).trim()

export async function resolveMessageAttachmentResource(resourceStore, sessionId, attachment) {
  const resourceId = attachmentResourceId(attachment)
  if (!sessionId || !resourceId) throw new Error('附件资源不可用')
  if (resourceStore.activeSessionId !== sessionId) throw new Error('附件不属于当前会话')

  let resource = resourceStore.sessionState(sessionId)?.resources
    ?.find(item => item.resource_id === resourceId)
  if (!resource) {
    await resourceStore.loadCatalog(sessionId)
    if (resourceStore.activeSessionId !== sessionId) throw new Error('附件不属于当前会话')
    resource = resourceStore.sessionState(sessionId)?.resources
      ?.find(item => item.resource_id === resourceId)
  }
  if (!resource || resource.role !== 'attachment' || resource.status !== 'active') {
    throw new Error('附件资源不可用')
  }
  return resource
}

export const isImageAttachmentResource = resource => (
  resource?.renderer === 'image' || String(resource?.media_type || '').startsWith('image/')
)
