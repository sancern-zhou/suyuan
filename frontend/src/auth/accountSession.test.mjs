import test from 'node:test'
import assert from 'node:assert/strict'
import { createApp, ref } from 'vue'
import { createPinia, defineStore } from 'pinia'
import { setAccountIdentity, accountStateKey, accountGeneration, assertAccountGeneration } from './accountSession.js'
import { installAccountStoreReset } from './accountStoreReset.js'
import { createAuthFetch } from './http.js'
import { createAuthSession } from './authStore.js'

test('state keys isolate project/account and resets replace nested option and setup state', () => {
  const pinia = createPinia()
  let stopped = 0
  const dispose = installAccountStoreReset(pinia, () => { stopped += 1 })
  createApp({}).use(pinia)
  const options = defineStore('options', { state: () => ({ sessions: {} }) })(pinia)
  const setup = defineStore('setup', () => ({ messages: ref([]) }))(pinia)
  setAccountIdentity({ id: 'A' })
  const keyA = accountStateKey('project', 'mode')
  options.sessions.A = { content: 'private' }
  setup.messages.push('private')
  const oldGeneration = accountGeneration()
  setAccountIdentity({ id: 'B' })
  assert.notEqual(accountStateKey('project', 'mode'), keyA)
  assert.notEqual(accountStateKey('another-project', 'mode'), accountStateKey('project', 'mode'))
  assert.deepEqual(options.sessions, {})
  assert.deepEqual(setup.messages, [])
  assert.throws(() => assertAccountGeneration(oldGeneration), { name: 'AbortError' })
  assert.equal(stopped, 2)
  dispose()
})

test('response body from a previous account is rejected even after response headers arrived', async () => {
  setAccountIdentity({ id: 'A' })
  let resolveBody
  const response = new Response('{}')
  response.json = () => new Promise(resolve => { resolveBody = resolve })
  const fetch = createAuthFetch({ fetchImpl: async () => response, storage: { readSession: () => ({ token: 'A' }) } })
  const received = await fetch('/api/private')
  const pending = received.json()
  setAccountIdentity({ id: 'B' })
  resolveBody({ private: 'A' })
  await assert.rejects(pending, { name: 'AbortError' })
})

test('failed current-user lookup clears the half-established login', async () => {
  let cleared = false
  const session = createAuthSession({
    storage: { readSession: () => ({}), clear: () => { cleared = true } },
    api: { login: async () => ({ result: { accessToken: 'new' } }), currentUser: async () => { throw new Error('failed') } }
  })
  await assert.rejects(session.login({}), /failed/)
  assert.equal(session.token, '')
  assert.equal(session.user, null)
  assert.equal(cleared, true)
})
