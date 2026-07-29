const STORAGE_PREFIX = 'chat-composer-selection:'

export function createSelectionRestoreGuard() {
  let generation = 0

  return {
    begin(sessionId, mode) {
      return {
        generation: ++generation,
        sessionId: sessionId || null,
        mode: mode || null
      }
    },
    invalidate() {
      generation += 1
    },
    isCurrent(token, sessionId, mode) {
      return Boolean(token) &&
        token.generation === generation &&
        token.sessionId === (sessionId || null) &&
        token.mode === (mode || null)
    }
  }
}

export function reconcileSelectionDraft(draft, skills = [], resources = []) {
  const skill = skills.find(item => item.id === draft?.skillId && item.compatible !== false) || null
  const resourceById = new Map(resources.map(item => [item.id, item]))
  const files = (draft?.fileIds || []).map(id => resourceById.get(id)).filter(Boolean)
  return { skill, files }
}

export function readSelectionDraft(sessionId, storage = globalThis.localStorage) {
  if (!sessionId || !storage) return { skillId: null, fileIds: [] }
  try {
    const parsed = JSON.parse(storage.getItem(`${STORAGE_PREFIX}${sessionId}`) || '{}')
    return {
      skillId: typeof parsed.skillId === 'string' ? parsed.skillId : null,
      fileIds: Array.isArray(parsed.fileIds) ? parsed.fileIds.map(String) : []
    }
  } catch {
    return { skillId: null, fileIds: [] }
  }
}

export function writeSelectionDraft(sessionId, draft, storage = globalThis.localStorage) {
  if (!sessionId || !storage) return
  const normalized = {
    skillId: draft?.skillId || null,
    fileIds: Array.from(new Set(draft?.fileIds || []))
  }
  const key = `${STORAGE_PREFIX}${sessionId}`
  if (!normalized.skillId && normalized.fileIds.length === 0) {
    storage.removeItem(key)
    return
  }
  storage.setItem(key, JSON.stringify(normalized))
}
