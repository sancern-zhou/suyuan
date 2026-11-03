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


function fakeEntryEnvironment(href) {
  const url = new URL(href)
  const location = {
    get href() { return url.href },
    get origin() { return url.origin },
    get search() { return url.search },
    get hash() { return url.hash }
  }
  const history = {
    state: null,
    replaceState(state, title, newUrl) { url.href = new URL(newUrl, url.href).href }
  }
  return { location, history }
}


test('an entry token from the unified platform establishes a session without login', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  const calls = []
  const api = {
    currentUser: async token => {
      calls.push(token)
      return { result: { id: 'u9', userName: 'zhangsan', name: '张三' } }
    }
  }
  const { location, history } = fakeEntryEnvironment('http://11.54.200.200:5175/?token=portal-token&from=portal')
  const session = createAuthSession({ api, storage, sysCode: 'SUYUAN', entryLocation: location, entryHistory: history })

  const user = await session.bootstrap()

  assert.equal(user.id, 'u9')
  assert.equal(session.token, 'portal-token')
  assert.deepEqual(raw.dump()['Access-Token'], 'portal-token')
  assert.deepEqual(calls, ['portal-token'])
  // 地址栏中的 token 已被清洗
  assert.equal(location.href, 'http://11.54.200.200:5175/?from=portal')
})


test('a rejected entry token falls back to the persisted session', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  storage.writeSession({ token: 'local-token', sysCode: 'SUYUAN', user: { id: 'u1' } })
  const calls = []
  const api = {
    currentUser: async token => {
      calls.push(token)
      if (token === 'stale-entry-token') throw new Error('company authentication rejected')
      return { result: { id: 'u1' } }
    }
  }
  const { location, history } = fakeEntryEnvironment('http://11.54.200.200:5175/?token=stale-entry-token')
  const session = createAuthSession({ api, storage, sysCode: 'SUYUAN', entryLocation: location, entryHistory: history })

  const user = await session.bootstrap()

  assert.equal(user.id, 'u1')
  assert.equal(session.token, 'local-token')
  assert.deepEqual(calls, ['stale-entry-token', 'local-token'])
  assert.equal(location.href, 'http://11.54.200.200:5175/')
})


test('a rejected entry token without a local session lands on the login route', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  const api = {
    currentUser: async () => { throw new Error('rejected') }
  }
  const { location, history } = fakeEntryEnvironment('http://11.54.200.200:5175/?token=bad-token')
  const session = createAuthSession({ api, storage, sysCode: 'SUYUAN', entryLocation: location, entryHistory: history })

  assert.equal(await session.bootstrap(), null)
  assert.equal(session.token, '')
  assert.equal(location.href, 'http://11.54.200.200:5175/')
})


test('an oauth authorization code is exchanged and establishes the session', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  const userCalls = []
  const exchangeCalls = []
  const api = {
    currentUser: async token => {
      userCalls.push(token)
      return { result: { id: 'u7', userName: 'zhangsan', name: '张三' } }
    }
  }
  const oauthApi = {
    exchangeCode: async (code, redirectUri) => {
      exchangeCalls.push([code, redirectUri])
      return { accessToken: 'oauth-access-token', refreshToken: 'refresh-1', expiresIn: 3600 }
    }
  }
  const { location, history } = fakeEntryEnvironment(
    'http://11.54.200.200:5175/?code=one-time-code&state=portal'
  )
  const session = createAuthSession({
    api,
    storage,
    sysCode: 'SUYUAN',
    oauthApi,
    entryLocation: location,
    entryHistory: history
  })

  const user = await session.bootstrap()

  assert.equal(user.id, 'u7')
  assert.equal(session.token, 'oauth-access-token')
  assert.deepEqual(raw.dump()['Access-Token'], 'oauth-access-token')
  assert.deepEqual(exchangeCalls, [['one-time-code', 'http://11.54.200.200:5175/']])
  assert.deepEqual(userCalls, ['oauth-access-token'])
  assert.equal(location.href, 'http://11.54.200.200:5175/')
})


test('a failed oauth exchange without a local session lands on the login route', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  const api = {
    currentUser: async () => { throw new Error('should not be called') }
  }
  const oauthApi = {
    exchangeCode: async () => { throw new Error('oauth_not_configured') }
  }
  const { location, history } = fakeEntryEnvironment('http://11.54.200.200:5175/?code=bad-code')
  const session = createAuthSession({
    api,
    storage,
    sysCode: 'SUYUAN',
    oauthApi,
    entryLocation: location,
    entryHistory: history
  })

  assert.equal(await session.bootstrap(), null)
  assert.equal(session.token, '')
  assert.equal(location.href, 'http://11.54.200.200:5175/')
})


test('session identity is resolved through the gateway session api', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  storage.writeSession({ token: 'oauth-access-token', sysCode: 'SUYUAN', user: null })
  const platformCalls = []
  const api = {
    currentUser: async token => {
      platformCalls.push(token)
      throw new Error('platform direct call must not be used')
    }
  }
  const meCalls = []
  const sessionApi = {
    me: async token => {
      meCalls.push(token)
      return { result: { id: 'u1', userName: 'zhangsan', name: '张三' } }
    }
  }
  const session = createAuthSession({ api, storage, sysCode: 'SUYUAN', sessionApi })

  const user = await session.bootstrap()

  assert.equal(user.id, 'u1')
  assert.deepEqual(meCalls, ['oauth-access-token'])
  assert.deepEqual(platformCalls, [])
})


test('a jwt-shaped entry token is exchanged before establishing the session', async () => {
  const raw = memoryStorage()
  const storage = createAuthStorage(raw)
  const jwtLoginCalls = []
  const api = {
    currentUser: async () => ({ result: { id: 'u3', userName: 'lisi', name: '李四' } })
  }
  const oauthApi = {
    jwtLogin: async token => {
      jwtLoginCalls.push(token)
      return { accessToken: 'minted-access-token', refreshToken: 'refresh-1', expiresIn: 3600 }
    }
  }
  const { location, history } = fakeEntryEnvironment('http://11.54.200.200:5175/?token=eyJhbGciOiJIUzI1NiJ9.a.b')
  const session = createAuthSession({
    api, storage, sysCode: 'SUYUAN', oauthApi,
    entryLocation: location, entryHistory: history
  })

  const user = await session.bootstrap()

  assert.equal(user.id, 'u3')
  assert.equal(session.token, 'minted-access-token')
  assert.deepEqual(jwtLoginCalls, ['eyJhbGciOiJIUzI1NiJ9.a.b'])
  assert.equal(location.href, 'http://11.54.200.200:5175/')
})
