export const attachmentResourceId = attachment => String(
  attachment?.resource_id
  || attachment?.resourceRefId
  || attachment?.resource_ref?.resource_id
  || attachment?.resource_ref?.ref_id
  || ''
).trim()

// 消息内资源卡的“面板打开”复用本解析器：除用户上传附件外，还包括
// Agent 产出的产品资源（报告/展示页/文件），与后端可见角色集合一致。
const PREVIEWABLE_ROLES = new Set(['attachment', 'output', 'report'])

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
  if (!resource || !PREVIEWABLE_ROLES.has(resource.role) || resource.status !== 'active') {
    throw new Error('附件资源不可用')
  }
  return resource
}

export const isImageAttachmentResource = resource => (
  resource?.renderer === 'image' || String(resource?.media_type || '').startsWith('image/')
)
