import assert from 'node:assert/strict'
import test from 'node:test'
import { createPinia } from 'pinia'

import { useAuthStore } from './authStore.js'
import { createAuthGuard, safeRedirect } from './routerGuard.js'


function store(overrides = {}) {
  return {
    token: '',
    user: null,
    initialized: false,
    get isAuthenticated() { return Boolean(this.token && this.user) },
    async bootstrap() { this.initialized = true; return this.user },
    ...overrides
  }
}


test('protected route bootstraps once and reuses an existing platform session', async () => {
  let calls = 0
  const auth = store({
    token: 'platform-token',
    async bootstrap() {
      calls += 1
      this.user = { id: 'u1' }
      this.initialized = true
      return this.user
    }
  })
  const guard = createAuthGuard(auth)

  assert.equal(await guard({ path: '/', fullPath: '/' }), true)
  assert.equal(await guard({ path: '/knowledge-base', fullPath: '/knowledge-base' }), true)
  assert.equal(calls, 1)
})


test('invalid session redirects to login with a same-origin return path', async () => {
  const auth = store({
    async bootstrap() { this.initialized = true; throw new Error('invalid') }
  })

  assert.deepEqual(
    await createAuthGuard(auth)({ path: '/session/1', fullPath: '/session/1?tab=a' }),
    { path: '/login', query: { redirect: '/session/1?tab=a' } }
  )
})


test('authenticated users leave login for a validated redirect', async () => {
  const auth = store({ token: 'token', user: { id: 'u1' }, initialized: true })
  const guard = createAuthGuard(auth)

  assert.equal(
    await guard({ path: '/login', fullPath: '/login', query: { redirect: '/tools-management' } }),
    '/tools-management'
  )
  assert.equal(
    await guard({ path: '/login', fullPath: '/login', query: { redirect: '//evil.test' } }),
    '/'
  )
})


test('safeRedirect permits only local absolute paths', () => {
  assert.equal(safeRedirect('/knowledge-base?x=1'), '/knowledge-base?x=1')
  assert.equal(safeRedirect('//evil.test'), '/')
  assert.equal(safeRedirect('https://evil.test'), '/')
  assert.equal(safeRedirect('\\evil.test'), '/')
})


test('mock administrator enters protected routes without a company token', async () => {
  const auth = useAuthStore(createPinia())
  auth.authMode = 'mock'
  auth.user = { id: 'local-developer', isAdmin: true }
  auth.initialized = true

  assert.equal(
    await createAuthGuard(auth)({ path: '/knowledge-base', fullPath: '/knowledge-base' }),
    true
  )
})
