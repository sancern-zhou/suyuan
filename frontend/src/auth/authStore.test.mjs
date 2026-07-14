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
