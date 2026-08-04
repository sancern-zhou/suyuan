import assert from 'node:assert/strict'
import test from 'node:test'

import { createCompanyCrypto } from './companyCrypto.js'


test('company login matches the 2.1.4 SM2/SM3/SM4 protocol layout', () => {
  const crypto = createCompanyCrypto(
    {
      encryptType: 'SM2',
      sm2PublicKey: 'public-key',
      sm4Key: '0123456789abcdef' // gitleaks:allow -- deterministic test fixture
    },
    {
      sm2Encrypt: value => `sm2(${value})`,
      sm3Hash: value => `sm3(${value})`,
      sm4Encrypt: value => `sm4(${value})`,
      now: () => 1700000000000,
      uuid: () => 'fixed-uuid'
    }
  )

  const request = crypto.loginRequest('zhangsan', 'password', 'existing-token', {
    verifyCode: '1234',
    captchaKey: 'captcha-key'
  })

  assert.deepEqual(request.body, {
    secretName: 'sm2(zhangsan)',
    secretCode: 'sm2(password)',
    isEncry: true,
    verifyCode: '1234',
    captchaKey: 'captcha-key',
    isLog: '1',
    logType: '5'
  })
  assert.equal(
    request.headers.Sign,
    'sm4(sm3(/auth/token/authentication,1700000000000,existing-token),1700000000000,existing-token,fixed-uuid)'
  )
  assert.equal(request.headers.encryptType, 'sm4(SM2)')
  assert.equal(request.headers['Content-Type'], 'application/json;charset=UTF-8')
})


test('company crypto delegates SM2 encryption to the approved module adapter', () => {
  const encryptedValues = []
  const crypto = createCompanyCrypto(
    { encryptType: 'SM2', sm2PublicKey: 'key', sm4Key: '0123456789abcdef' }, // gitleaks:allow -- deterministic test fixture
    {
      sm2Encrypt: value => { encryptedValues.push(value); return 'cipher' },
      sm3Hash: () => 'hash',
      sm4Encrypt: value => value,
      now: () => 1,
      uuid: () => 'uuid'
    }
  )

  crypto.loginRequest('user', 'password', '')

  assert.deepEqual(encryptedValues, ['user', 'password'])
})


test('company login includes captcha and login audit fields', () => {
  const crypto = createCompanyCrypto(
    { encryptType: 'SM2' },
    {
      sm2Encrypt: value => `sm2:${value}`,
      sm3Hash: value => `sm3:${value}`,
      sm4Encrypt: value => `sm4:${value}`,
      now: () => 1,
      uuid: () => 'uuid'
    }
  )

  const request = crypto.loginRequest('user', 'password', '', {
    verifyCode: '2468',
    captchaKey: 'captcha-key'
  })

  assert.deepEqual(request.body, {
    secretName: 'sm2:user',
    secretCode: 'sm2:password',
    isEncry: true,
    verifyCode: '2468',
    captchaKey: 'captcha-key',
    isLog: '1',
    logType: '5'
  })
})
