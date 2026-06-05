import assert from 'node:assert/strict'
import { createImagePanelLightboxImage } from './imagePanelLightbox.js'

assert.equal(
  createImagePanelLightboxImage('', '分析图片'),
  null,
  'empty image source should not open lightbox'
)

assert.deepEqual(
  createImagePanelLightboxImage('data:image/png;base64,abc', '浓度趋势图'),
  {
    src: 'data:image/png;base64,abc',
    alt: '浓度趋势图'
  },
  'loaded image source should be passed to lightbox with alt text'
)

assert.deepEqual(
  createImagePanelLightboxImage('/api/image/chart_1', ''),
  {
    src: '/api/image/chart_1',
    alt: '分析图片'
  },
  'missing alt should fall back to default image label'
)

console.log('imagePanelLightbox tests passed')
