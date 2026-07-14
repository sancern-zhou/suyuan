import assert from 'node:assert/strict'
import test from 'node:test'

import { encryptSM2 } from './SM2.js'
import { decryptSM4, encryptSM4 } from './SM4.js'


test('SM2 output uses an unprefixed C1C3C2 cipher', () => {
  const plaintext = 'ScGuanLy'
  const encrypted = encryptSM2(plaintext)

  assert.match(encrypted, /^[0-9a-f]+$/i)
  assert.equal(encrypted.length, 192 + Buffer.byteLength(plaintext) * 2)
})


test('SM4 uses the company CBC configuration and round trips UTF-8', () => {
  const value = 'SUYUAN-溯源'
  const encrypted = encryptSM4(value)

  assert.notEqual(encrypted, value)
  assert.equal(decryptSM4(encrypted), value)
})
