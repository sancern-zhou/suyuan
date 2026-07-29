import {
  createLatestMediaObjectUrlLoader,
  loadApiMediaObjectUrl,
  sameOriginApiMediaPath
} from '../services/apiMediaBlob.js'


function localImagePreview(source) {
  if (typeof source !== 'string') return null
  return source.startsWith('data:image/') || source.startsWith('blob:') ? source : null
}


export function createMessageAttachmentMedia({
  loadObjectUrl = loadApiMediaObjectUrl,
  revokeObjectURL = value => URL.revokeObjectURL(value),
  onChange = () => {},
  onError = (error, source) => console.error('附件图片加载失败:', source, error)
} = {}) {
  let url = ''
  const publish = (nextUrl) => {
    url = nextUrl
    onChange(nextUrl)
  }
  const loader = createLatestMediaObjectUrlLoader({ loadObjectUrl, revokeObjectURL })

  return {
    async setSource(source) {
      loader.clear()
      publish('')
      const path = sameOriginApiMediaPath(source)
      if (!path) {
        const preview = localImagePreview(source)
        if (preview) publish(preview)
        return preview
      }

      return loader.start(path, {
        onSuccess: publish,
        onError: error => onError(error, path)
      })
    },

    currentUrl() {
      return url
    },

    clear() {
      loader.clear()
      if (url) publish('')
    }
  }
}
