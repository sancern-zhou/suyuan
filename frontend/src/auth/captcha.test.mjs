import assert from 'node:assert/strict'
import test from 'node:test'

import { createCaptchaChallenge } from './captcha.js'


test('captcha challenge replaces the previous key and uses company type 1', () => {
  const challenge = createCaptchaChallenge({
    previousKey: 'old key',
    authBaseUrl: '/api',
    uuid: () => 'new-key',
    random: () => 0,
    now: () => 123
  })

  assert.equal(challenge.key, 'new-key')
  assert.equal(challenge.url, '/api/auth/token/captcha?oldKey=old+key&key=new-key&type=1&d=123')
})


test('captcha challenge uses company type 3 for the upper random bucket', () => {
  const challenge = createCaptchaChallenge({
    previousKey: '',
    authBaseUrl: '/api',
    uuid: () => 'key',
    random: () => 0.9,
    now: () => 456
  })

  assert.match(challenge.url, /type=3&d=456$/)
})
