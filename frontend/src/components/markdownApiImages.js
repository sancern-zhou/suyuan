import {
  apiImagePath,
  loadApiImageObjectUrl
} from '../services/apiImageBlob.js'

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function escapeRawHtmlImageTags(html) {
  if (typeof html !== 'string') return html
  return html.replace(/<img(?=[\s/>])/gi, '&lt;img')
}

export function deferredApiImageAttributes(source) {
  const path = apiImagePath(source)
  return path ? { 'data-api-image-src': path } : null
}

export function renderDeferredApiImage({
  src,
  alt = '',
  cssClass = 'md-external-image'
}) {
  const attributes = deferredApiImageAttributes(src)
  if (!attributes) return ''

  const escapedSource = escapeHtml(attributes['data-api-image-src'])
  const escapedAlt = escapeHtml(alt)
  const escapedClass = escapeHtml(cssClass)
  return `<div class="md-image-wrapper">
    <img data-api-image-src="${escapedSource}" alt="${escapedAlt}" class="${escapedClass}" />
    <p class="md-image-caption">${escapedAlt}</p>
  </div>`
}

export function createMarkdownApiImageHydrator({
  loadObjectUrl = loadApiImageObjectUrl,
  revokeObjectURL = value => URL.revokeObjectURL(value),
  onError = (error, source) => console.error('Markdown图片加载失败:', source, error)
} = {}) {
  let generation = 0
  const ownedUrls = new Set()

  const revokeOwnedUrls = () => {
    for (const url of ownedUrls) {
      revokeObjectURL(url)
    }
    ownedUrls.clear()
  }

  return {
    async hydrate(root) {
      const renderGeneration = ++generation
      revokeOwnedUrls()
      if (!root) return

      const images = Array.from(root.querySelectorAll('[data-api-image-src]'))
      await Promise.all(images.map(async (image) => {
        const source = image.getAttribute('data-api-image-src')
        if (!source) return

        try {
          const url = await loadObjectUrl(source)
          const imageStillExists = typeof root.contains !== 'function' || root.contains(image)
          if (renderGeneration !== generation || !imageStillExists) {
            revokeObjectURL(url)
            return
          }

          ownedUrls.add(url)
          image.setAttribute('src', url)
          image.removeAttribute('data-api-image-src')
        } catch (error) {
          if (renderGeneration === generation) {
            onError(error, source)
          }
        }
      }))
    },

    clear() {
      generation += 1
      revokeOwnedUrls()
    }
  }
}
