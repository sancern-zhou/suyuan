import assert from 'node:assert/strict'

import { listSessions } from './session.js'

const calls = []

globalThis.fetch = async (url, options = {}) => {
  calls.push({ url, options })
  return {
    ok: true,
    status: 200,
    json: async () => ({ sessions: [], total: 0 })
  }
}

await listSessions()
assert.equal(calls.at(-1).url, '/api/sessions/?limit=200')
assert.deepEqual(calls.at(-1).options, {
  method: 'GET',
  headers: {}
})

await listSessions({ limit: 25 })
assert.equal(calls.at(-1).url, '/api/sessions/?limit=25')

console.log('session API list limit tests passed')
