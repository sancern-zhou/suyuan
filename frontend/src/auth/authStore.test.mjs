import assert from 'node:assert/strict'
import test from 'node:test'

import { createAuthSession } from './authStore.js'
import { createAuthStorage } from './storage.js'


function memoryStorage() {
  const values = new Map()
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
    dump: () => Object.fromEntries(values)
  }
}


test('login persists only the standard token, system code, and user keys', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  const calls = []
  const api = {
    login: async credentials => {
      calls.push(['login', credentials])
      return { result: { accessToken: 'company-token' } }
    },
    currentUser: async token => {
      calls.push(['user', token])
      return { result: { id: 'u1', userName: 'zhangsan', name: '张三' } }
    }
  }
  const session = createAuthSession({ api, storage, sysCode: 'SUYUAN' })

  await session.login({ username: 'zhangsan', password: 'plain-password' })

  assert.equal(session.token, 'company-token')
  assert.equal(session.user.id, 'u1')
  assert.deepEqual(Object.keys(raw.dump()).sort(), [
    'Access-Sys-Code',
    'Access-Token',
    'Access-User'
  ])
  assert.equal(JSON.stringify(raw.dump()).includes('plain-password'), false)
  assert.deepEqual(calls, [
    ['login', { username: 'zhangsan', password: 'plain-password' }],
    ['user', 'company-token']
  ])
})


test('bootstrap reuses a same-origin platform token and logout clears local state', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  storage.writeSession({ token: 'platform-token', sysCode: 'SUYUAN', user: null })
  const api = {
    currentUser: async token => ({ result: { id: 'u2', token } }),
    logout: async token => ({ token })
  }
  const session = createAuthSession({ api, storage, sysCode: 'SUYUAN' })

  assert.equal((await session.bootstrap()).id, 'u2')
  await session.logout()

  assert.equal(session.token, '')
  assert.equal(session.user, null)
  assert.deepEqual(raw.dump(), {})
})


test('adoptSession persists an externally issued token and skips the login API', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  const calls = []
  const api = {
    login: async () => calls.push('login'),
    currentUser: async () => calls.push('currentUser')
  }
  const session = createAuthSession({ api, storage, sysCode: 'SUYUAN' })

  const adopted = session.adoptSession({
    token: 'sso-token',
    sysCode: 'SUYUAN',
    user: { id: 'u3', userName: 'lisi' }
  })

  assert.equal(adopted.id, 'u3')
  assert.equal(session.token, 'sso-token')
  assert.equal(session.authMode, 'company')
  assert.equal(session.initialized, true)
  assert.deepEqual(calls, [])
  assert.deepEqual(
    { token: raw.dump()['Access-Token'], sysCode: raw.dump()['Access-Sys-Code'] },
    { token: 'sso-token', sysCode: 'SUYUAN' }
  )
  assert.equal(JSON.parse(raw.dump()['Access-User']).id, 'u3')
})


test('adoptSession rejects an incomplete payload and keeps the current session', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  const session = createAuthSession({ api: {}, storage, sysCode: 'SUYUAN' })

  assert.throws(() => session.adoptSession({ token: '', user: { id: 'u3' } }), /不完整/)
  assert.throws(() => session.adoptSession({ token: 't', user: {} }), /不完整/)
  assert.equal(session.token, '')
  assert.deepEqual(raw.dump(), {})
})


test('mock mode clears persisted company state and bootstraps the in-memory administrator', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  storage.writeSession({
    token: 'old-company-token',
    sysCode: 'SUYUAN',
    user: { id: 'old-user' }
  })
  const calls = []
  const mockUser = {
    id: 'local-developer',
    roleCodes: ['SUYUAN_ADMIN'],
    isAdmin: true
  }
  const api = {
    login: async () => calls.push('login'),
    currentUser: async () => calls.push('currentUser'),
    logout: async () => calls.push('logout')
  }
  const session = createAuthSession({
    api,
    storage,
    sysCode: 'SUYUAN',
    authMode: 'mock',
    mockUser
  })

  assert.deepEqual(raw.dump(), {})
  assert.equal(await session.bootstrap(), mockUser)
  assert.equal(session.token, '')
  assert.equal(session.user, mockUser)
  assert.deepEqual(await session.login({}), mockUser)
  await session.logout()
  assert.equal(session.user, mockUser)
  assert.deepEqual(calls, [])
  assert.deepEqual(raw.dump(), {})
})
