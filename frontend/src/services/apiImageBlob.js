import { authFetch } from '../auth/http.js'

const API_IMAGE_PREFIX = '/api/image/'

export function apiImagePath(source) {
  if (typeof source !== 'string') return null

  if (source.startsWith(API_IMAGE_PREFIX) && source.length > API_IMAGE_PREFIX.length) {
    return source
  }

  if (source.startsWith('[IMAGE:') && source.endsWith(']')) {
    const imageId = source.slice(7, -1)
    return imageId ? `${API_IMAGE_PREFIX}${encodeURIComponent(imageId)}` : null
  }

  return null
}

export async function loadApiImageObjectUrl(source, {
  fetchImage = authFetch,
  createObjectURL = value => URL.createObjectURL(value)
} = {}) {
  const path = apiImagePath(source)
  if (!path) {
    throw new Error(`Unsupported API image source: ${source}`)
  }

  const response = await fetchImage(path)
  if (!response.ok) {
    throw new Error(`Image request failed: HTTP ${response.status}`)
  }

  const contentType = response.headers.get('Content-Type') || ''
  if (!contentType.toLowerCase().startsWith('image/')) {
    throw new Error(`Image response is not an image: ${contentType || 'unknown content type'}`)
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

export function createLatestImageObjectUrlLoader({
  loadObjectUrl = loadApiImageObjectUrl,
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
