import test from 'node:test'
import assert from 'node:assert/strict'

import { getOnboardingStep, scanOwnerLabel } from './createAccountFlow.js'

test('new flow goes directly from QR to completion', () => {
  assert.equal(getOnboardingStep({ scanCreated: false, scanConfirmed: false }), 'starting')
  assert.equal(getOnboardingStep({ scanCreated: true, scanConfirmed: false }), 'qrcode')
  assert.equal(getOnboardingStep({ scanCreated: true, scanConfirmed: true }), 'complete')
})

test('owner label comes from server-authenticated identity', () => {
  assert.equal(
    scanOwnerLabel({ platform_display_name: 'Alice', platform_username: 'alice' }),
    'Alice（alice）'
  )
})
