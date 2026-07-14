import assert from 'node:assert/strict'
import test from 'node:test'

import { createAuthApi } from './authApi.js'


function successfulResponse(result = {}) {
  return {
    ok: true,
    json: async () => ({ state: 0, success: true, result })
  }
}


test('company authentication endpoints use JCXT while business sessions remain separate', async () => {
  const requests = []
  const fetchImpl = async (url, options = {}) => {
    requests.push({ url, options })
    return successfulResponse(url.includes('authentication') ? { accessToken: 'token' } : {})
  }
  const storage = {
    readSession: () => ({ token: '', sysCode: 'SUYUAN' })
  }
  const api = createAuthApi({
    fetchImpl,
    storage,
    config: {
      authBaseUrl: '/api',
      authPlatformSysCode: 'JCXT',
      businessSysCode: 'SUYUAN',
      encryptType: 'SM2'
    }
  })

  await api.login({ username: 'user', password: 'password', verifyCode: '1234', captchaKey: 'key' })
  await api.currentUser('token')
  await api.logout('token')

  assert.deepEqual(requests.map(request => request.options.headers.SysCode), [
    'JCXT',
    'JCXT',
    'JCXT'
  ])
  assert.equal(storage.readSession().sysCode, 'SUYUAN')
})
