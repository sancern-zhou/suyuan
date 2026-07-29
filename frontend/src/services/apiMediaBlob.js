import { authFetch } from '../auth/http.js'


const SAME_ORIGIN_API_PREFIX = '/api/'
const LEGACY_IMAGE_PREFIX = '[IMAGE:'


function legacyImagePlaceholderPath(source) {
  if (!source.startsWith(LEGACY_IMAGE_PREFIX) || !source.endsWith(']')) return null
  const imageId = source.slice(LEGACY_IMAGE_PREFIX.length, -1)
  return imageId ? `/api/image/${encodeURIComponent(imageId)}` : null
}


export function sameOriginApiMediaPath(source) {
  if (typeof source !== 'string') return null

  const legacyPath = legacyImagePlaceholderPath(source)
  if (legacyPath) return legacyPath

  if (source.startsWith(SAME_ORIGIN_API_PREFIX) && source.length > SAME_ORIGIN_API_PREFIX.length) {
    return source
  }

  return null
}


export async function loadApiMediaObjectUrl(source, {
  fetchMedia = authFetch,
  createObjectURL = value => URL.createObjectURL(value)
} = {}) {
  const path = sameOriginApiMediaPath(source)
  if (!path) {
    throw new Error(`Unsupported same-origin API media source: ${source}`)
  }

  const response = await fetchMedia(path)
  if (!response.ok) {
    throw new Error(`Media request failed: HTTP ${response.status}`)
  }

  const contentType = response.headers.get('Content-Type') || ''
  if (!contentType.toLowerCase().startsWith('image/')) {
    throw new Error(`Media response is not an image: ${contentType || 'unknown content type'}`)
  }

  return createObjectURL(await response.blob())
}


function readBlobWithFileReader(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(reader.error || new Error('Failed to read image Blob'))
    reader.readAsDataURL(blob)
  })
}


export async function objectUrlToDataUrl(objectUrl, {
  fetchObjectUrl = value => fetch(value),
  readBlobAsDataUrl = readBlobWithFileReader
} = {}) {
  const response = await fetchObjectUrl(objectUrl)
  if (!response.ok) {
    throw new Error(`Object URL request failed: HTTP ${response.status}`)
  }

  const dataUrl = await readBlobAsDataUrl(await response.blob())
  if (typeof dataUrl !== 'string' || !dataUrl.startsWith('data:image/')) {
    throw new Error('Object URL did not produce an image data URL')
  }
  return dataUrl
}


export function createLatestMediaObjectUrlLoader({
  loadObjectUrl = loadApiMediaObjectUrl,
  revokeObjectURL = value => URL.revokeObjectURL(value)
} = {}) {
  let generation = 0
  let currentUrl = null

  const clearCurrentUrl = () => {
    if (!currentUrl) return
    revokeObjectURL(currentUrl)
    currentUrl = null
  }

  return {
    async start(source, {
      onSuccess,
      onError,
      onSettled
    } = {}) {
      const requestGeneration = ++generation

      try {
        const url = await loadObjectUrl(source)
        if (requestGeneration !== generation) {
          revokeObjectURL(url)
          return null
        }

        clearCurrentUrl()
        currentUrl = url
        onSuccess?.(url)
        return url
      } catch (error) {
        if (requestGeneration === generation) {
          onError?.(error)
        }
        return null
      } finally {
        if (requestGeneration === generation) {
          onSettled?.()
        }
      }
    },

    clear() {
      generation += 1
      clearCurrentUrl()
    }
  }
}
