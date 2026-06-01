import assert from 'node:assert/strict'
import {
  buildBindInstruction,
  getOnboardingStep,
  isUserBound,
} from './createAccountFlow.js'

assert.equal(buildBindInstruction({ bind_instruction: '8327' }), '8327')
assert.equal(buildBindInstruction({ bind_code: '9146' }), '9146')
assert.equal(isUserBound({ status: 'active' }), true)
assert.equal(isUserBound({ status: 'pending_bind' }), false)
assert.equal(getOnboardingStep({ pendingUser: null }), 'profile')
assert.equal(getOnboardingStep({ pendingUser: { id: 'u1' }, loginSuccess: false }), 'qrcode')
assert.equal(getOnboardingStep({ pendingUser: { id: 'u1' }, loginSuccess: true, bound: false }), 'binding')
assert.equal(getOnboardingStep({ pendingUser: { id: 'u1' }, loginSuccess: true, bound: true }), 'complete')

console.log('createAccountFlow tests passed')
