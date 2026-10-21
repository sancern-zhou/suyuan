// Account identity and request generation are shared by stores and transports.
let identity = null
let generation = 0
const listeners = new Set()

export const accountGeneration = () => generation
export const accountStateKey = (project, name) => identity
  ? `account-state:${encodeURIComponent(project)}:${encodeURIComponent(identity)}:${name}`
  : null

export function setAccountIdentity(user, sysCode = 'SUYUAN') {
  const userId = user?.id || user?.userId
  const next = userId ? `${sysCode}:${userId}` : null
  if (next === identity) return
  identity = next
  generation += 1
  for (const listener of listeners) listener()
}

export const onAccountChanged = listener => {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function assertAccountGeneration(expected) {
  if (expected !== generation) throw new DOMException('Account changed', 'AbortError')
}

export function discardLegacyConversationState(storage) {
  const keys = Array.from({ length: storage.length || 0 }, (_, index) => storage.key(index))
  for (const key of keys) {
    if (key === 'current-mode' || key?.startsWith('mode-state-')) storage.removeItem(key)
  }
}
