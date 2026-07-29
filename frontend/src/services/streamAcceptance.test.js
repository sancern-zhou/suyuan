import assert from 'node:assert/strict'
import test from 'node:test'

import { acceptStreamResponse } from './streamAcceptance.js'

test('notifies acceptance only after an ok streaming response exists', () => {
  let accepted = 0
  const body = {}
  assert.equal(acceptStreamResponse({ ok: true, body }, () => { accepted += 1 }), body)
  assert.equal(accepted, 1)
})

test('does not notify acceptance for rejected or bodyless responses', () => {
  let accepted = 0
  assert.throws(
    () => acceptStreamResponse({ ok: false, status: 422, body: {} }, () => { accepted += 1 }),
    /422/
  )
  assert.throws(
    () => acceptStreamResponse({ ok: true, body: null }, () => { accepted += 1 }),
    /null/
  )
  assert.equal(accepted, 0)
})
