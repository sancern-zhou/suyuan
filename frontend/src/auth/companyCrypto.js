import smCrypto from 'sm-crypto'
import { v4 as uuidv4 } from 'uuid'

import { encryptSM2 } from './SM2.js'
import { encryptSM4 } from './SM4.js'


function legacyBase64Password(value) {
  const encoded = globalThis.btoa(unescape(encodeURIComponent(value)))
  return [...encoded]
    .map(character => String.fromCharCode(character.charCodeAt(0) << 2))
    .join('')
}


export function createCompanyCrypto(config, dependencies = {}) {
  const sm2Encrypt = dependencies.sm2Encrypt || encryptSM2
  const sm3Hash = dependencies.sm3Hash || smCrypto.sm3
  const sm4Encrypt = dependencies.sm4Encrypt || encryptSM4
  const now = dependencies.now || Date.now
  const uuid = dependencies.uuid || uuidv4
  const encryptType = config.encryptType || 'SM2'

  function encryptSm2(value) {
    return sm2Encrypt(value)
  }

  function password(value) {
    if (encryptType === 'SM2') return encryptSm2(value)
    if (encryptType === 'SM4') return sm4Encrypt(value)
    return legacyBase64Password(value)
  }

  function sign(path, token = '') {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`
    const timestamp = now()
    const digest = sm3Hash(`${normalizedPath},${timestamp},${token}`)
    return sm4Encrypt(`${digest},${timestamp},${token},${uuid()}`)
  }

  function requestHeaders(path, token = '') {
    return {
      Sign: sign(path, token),
      encryptType: sm4Encrypt(encryptType),
      'Content-Type': 'application/json;charset=UTF-8'
    }
  }

  return {
    requestHeaders,
    loginRequest(username, plainPassword, token = '') {
      return {
        body: {
          secretName: encryptSm2(username),
          secretCode: password(plainPassword),
          isEncry: true
        },
        headers: requestHeaders('/auth/token/authentication', token)
      }
    }
  }
}


export function runtimeAuthConfig() {
  return {
    sysCode: 'SUYUAN',
    encryptType: 'SM2',
    authBaseUrl: '/api',
    ...(globalThis.window?.__SUYUAN_AUTH_CONFIG__ || {})
  }
}
