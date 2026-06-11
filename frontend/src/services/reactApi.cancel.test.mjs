import assert from 'node:assert/strict'

import { agentAPI } from './reactApi.js'

let fetchCalled = false
let resolveFetch
globalThis.fetch = async () => {
  fetchCalled = true
  return new Promise((resolve) => {
    resolveFetch = () => resolve({ ok: true })
  })
}

let aborted = false
const controller = {
  abort() {
    aborted = true
  }
}

agentAPI.controllers.set('session_a', controller)
agentAPI.controller = controller

await agentAPI.cancel('session_a')

assert.equal(aborted, true)
assert.equal(agentAPI.controllers.has('session_a'), false)
assert.equal(agentAPI.controller, null)
assert.equal(fetchCalled, true)

resolveFetch()

console.log('react API cancel aborts locally before waiting for backend')
