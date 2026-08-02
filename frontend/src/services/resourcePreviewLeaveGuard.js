let activeGuard = null
let activeOwner = null

export function registerResourcePreviewLeaveGuard(owner, guard) {
  activeOwner = owner
  activeGuard = typeof guard === 'function' ? guard : null
  return () => {
    if (activeOwner !== owner) return
    activeOwner = null
    activeGuard = null
  }
}

export async function confirmResourcePreviewLeave() {
  if (!activeGuard) return true
  return (await activeGuard()) !== false
}

export function hasResourcePreviewLeaveGuard() {
  return Boolean(activeGuard)
}
