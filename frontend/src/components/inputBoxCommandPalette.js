const TRIGGER_PATTERN = /(^|\s)([/@])([^\s/@]*)$/u

export function findComposerTrigger(value, cursorPosition) {
  const text = String(value || '')
  const cursor = Math.max(0, Math.min(Number(cursorPosition) || 0, text.length))
  const match = text.slice(0, cursor).match(TRIGGER_PATTERN)
  if (!match) return null

  const symbol = match[2]
  return {
    type: symbol === '/' ? 'skill' : 'file',
    symbol,
    start: (match.index || 0) + match[1].length,
    search: match[3] || ''
  }
}

export function normalizeSkills(response) {
  const skills = response?.data?.skills || response?.skills || []
  return skills
    .filter(skill => skill && skill.enabled !== false && !skill.is_draft)
    .map(skill => ({
      id: String(skill.id || skill.slug || String(skill.file || '').split('/').pop()?.replace(/\.md$/i, '') || skill.name),
      name: String(skill.name || skill.id || ''),
      description: String(skill.description || ''),
      aliases: Array.isArray(skill.aliases) ? skill.aliases : [],
      compatible: skill.compatible !== false,
      missingTools: Array.isArray(skill.missing_tools) ? skill.missing_tools : []
    }))
    .filter(skill => skill.id && skill.name)
}

export function normalizeConversationResources(response) {
  const resources = response?.resources || response?.data?.resources || []
  return resources
    .filter(resource => (
      resource &&
      resource.status === 'active' &&
      ['file', 'artifact'].includes(resource.kind)
    ))
    .map(resource => {
      const uploaded = resource.role === 'attachment' || resource.metadata?.source === 'user_upload'
      return {
        id: String(resource.ref_id),
        name: String(resource.label || resource.ref_id),
        kind: resource.kind,
        role: resource.role || 'output',
        source: uploaded ? 'user_upload' : 'agent_generated',
        group: uploaded ? '用户上传' : 'Agent 生成',
        createdAt: resource.created_at || null,
        turnSequence: resource.turn_sequence ?? null,
        metadata: resource.metadata || {}
      }
    })
    .sort((left, right) => {
      if (left.source !== right.source) return left.source === 'user_upload' ? -1 : 1
      const timeDelta = Date.parse(right.createdAt || 0) - Date.parse(left.createdAt || 0)
      if (Number.isFinite(timeDelta) && timeDelta !== 0) return timeDelta
      return (right.turnSequence ?? -1) - (left.turnSequence ?? -1)
    })
}

export function filterPaletteItems(items, search) {
  const needle = String(search || '').trim().toLocaleLowerCase()
  if (!needle) return items
  return items.filter(item => [item.name, item.description, ...(item.aliases || [])]
    .join('\n')
    .toLocaleLowerCase()
    .includes(needle))
}

export function removeComposerTrigger(value, trigger, cursorPosition) {
  if (!trigger) return { value, cursor: cursorPosition }
  const text = String(value || '')
  const cursor = Math.max(trigger.start, Math.min(Number(cursorPosition) || 0, text.length))
  return {
    value: text.slice(0, trigger.start) + text.slice(cursor),
    cursor: trigger.start
  }
}

export function buildComposerPayload({
  query,
  skill,
  files,
  agentMode,
  modelTier,
  knowledgeBaseIds
}) {
  const turnFiles = (files || []).filter(file => !file.pinnedPolicy)
  const messageAttachments = turnFiles.map(file => ({
    ...(file.fileId ? { file_id: file.fileId } : {}),
    name: file.name,
    type: file.type === 'image' ? 'image' : 'file',
    ...(file.mimeType ? { mime_type: file.mimeType } : {}),
    ...(file.url ? { url: file.url } : {})
  }))
  return {
    query: String(query || ''),
    skillIds: skill ? [skill.id] : [],
    activeContexts: [
      ...(skill ? [{ type: 'skill', id: skill.id, label: skill.name }] : []),
      ...(files || [])
        .filter(file => file.pinnedPolicy)
        .map(file => ({ type: 'fixed_policy', id: file.id, label: file.name }))
    ],
    contextRefs: turnFiles.map(file => ({
      type: 'conversation_file',
      resource_id: file.id,
      display_name: file.name
    })),
    messageAttachments,
    agentMode,
    modelTier,
    knowledgeBaseIds: knowledgeBaseIds || []
  }
}

export function shouldClearAcceptedComposer(sent, current) {
  if (!sent || !current) return false
  const sentFiles = Array.isArray(sent.fileIds) ? sent.fileIds : []
  const currentFiles = Array.isArray(current.fileIds) ? current.fileIds : []
  return sent.query === current.query &&
    sent.skillId === current.skillId &&
    sentFiles.length === currentFiles.length &&
    sentFiles.every((id, index) => id === currentFiles[index])
}
