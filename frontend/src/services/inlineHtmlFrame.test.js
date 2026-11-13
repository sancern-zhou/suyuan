import test from 'node:test'
import assert from 'node:assert/strict'
import {
  FRAME_DEFAULT_HEIGHT,
  FRAME_MIN_HEIGHT,
  FRAME_PREVIEW_MAX_HEIGHT,
  isRuntimeHeightEvent,
  previewFrameHeight
} from './inlineHtmlFrame.js'

test('accepts only runtime height messages', () => {
  assert.equal(isRuntimeHeightEvent({ source: 'suyuan-html-runtime', type: 'height', height: 320 }), true)
  assert.equal(isRuntimeHeightEvent({ source: 'suyuan-html-runtime', type: 'height', height: '600' }), true)
  assert.equal(isRuntimeHeightEvent({ source: 'other-page', type: 'height', height: 320 }), false)
  assert.equal(isRuntimeHeightEvent({ source: 'suyuan-html-runtime', type: 'scroll', height: 320 }), false)
  assert.equal(isRuntimeHeightEvent({ source: 'suyuan-html-runtime', type: 'height', height: 0 }), false)
  assert.equal(isRuntimeHeightEvent({ source: 'suyuan-html-runtime', type: 'height', height: -40 }), false)
  assert.equal(isRuntimeHeightEvent({ source: 'suyuan-html-runtime', type: 'height', height: 'tall' }), false)
  assert.equal(isRuntimeHeightEvent(null), false)
  assert.equal(isRuntimeHeightEvent('height'), false)
})

test('preview height clamps into readable card bounds', () => {
  assert.equal(previewFrameHeight(0), FRAME_DEFAULT_HEIGHT)
  assert.equal(previewFrameHeight(undefined), FRAME_DEFAULT_HEIGHT)
  assert.equal(previewFrameHeight(80), FRAME_MIN_HEIGHT)
  assert.equal(previewFrameHeight(480), 480)
  assert.equal(previewFrameHeight(5000), FRAME_PREVIEW_MAX_HEIGHT)
  assert.equal(previewFrameHeight(320.6), 321)
})
