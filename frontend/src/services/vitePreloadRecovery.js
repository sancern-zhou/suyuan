const STORAGE_KEY = 'suyuan:vite-preload-reload-signatures'
const MAX_SIGNATURES = 20

function preloadErrorSignature(event) {
  const payload = event?.payload
  const message = payload?.message || String(payload || 'unknown-preload-error')
  return message.slice(0, 1000)
}

function readSignatures(storage) {
  try {
    const value = JSON.parse(storage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(value) ? value.filter(item => typeof item === 'string') : []
  } catch {
    return []
  }
}

export function registerVitePreloadRecovery(windowObject = window) {
  const handlePreloadError = event => {
    event.preventDefault()

    try {
      const storage = windowObject.sessionStorage
      const signature = preloadErrorSignature(event)
      const signatures = readSignatures(storage)
      if (signatures.includes(signature)) return

      storage.setItem(
        STORAGE_KEY,
        JSON.stringify([...signatures, signature].slice(-MAX_SIGNATURES))
      )
      windowObject.location.reload()
    } catch (error) {
      console.error('Unable to recover from a failed dynamic import', error)
    }
  }

  windowObject.addEventListener('vite:preloadError', handlePreloadError)
  return () => windowObject.removeEventListener('vite:preloadError', handlePreloadError)
}
