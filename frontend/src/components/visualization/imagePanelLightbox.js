export const createImagePanelLightboxImage = (src, alt) => {
  const imageSrc = String(src || '').trim()
  if (!imageSrc) return null

  return {
    src: imageSrc,
    alt: String(alt || '').trim() || '分析图片'
  }
}
