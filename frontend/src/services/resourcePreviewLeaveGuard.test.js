import assert from 'node:assert/strict'
import test from 'node:test'

import { confirmResourcePreviewLeave, registerResourcePreviewLeaveGuard } from './resourcePreviewLeaveGuard.js'

test('blocks leaving while the active preview guard rejects it', async () => {
  const unregister = registerResourcePreviewLeaveGuard('sheet', () => false)
  assert.equal(await confirmResourcePreviewLeave(), false)
  unregister()
  assert.equal(await confirmResourcePreviewLeave(), true)
})

test('an older preview cannot clear a newer preview guard', async () => {
  const clearOld = registerResourcePreviewLeaveGuard('old', () => false)
  const clearNew = registerResourcePreviewLeaveGuard('new', () => true)
  clearOld()
  assert.equal(await confirmResourcePreviewLeave(), true)
  clearNew()
})
