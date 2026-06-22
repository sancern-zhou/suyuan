import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveAMapConfig } from './amapConfig.js'

test('resolveAMapConfig falls back to backend config when env key is missing', async () => {
  const requested = []
  const config = await resolveAMapConfig({
    env: {},
    fetchImpl: async (url) => {
      requested.push(url)
      return {
        ok: true,
        async json () {
          return { amapPublicKey: 'backend-key' }
        }
      }
    }
  })

  assert.deepEqual(requested, ['/api/config'])
  assert.equal(config.key, 'backend-key')
})

test('resolveAMapConfig prefers Vite env key', async () => {
  const config = await resolveAMapConfig({
    env: {
      VITE_AMAP_KEY: 'env-key',
      VITE_AMAP_SECURITY_CODE: 'security-code'
    },
    fetchImpl: async () => {
      throw new Error('fetch should not be called')
    }
  })

  assert.equal(config.key, 'env-key')
  assert.equal(config.securityJsCode, 'security-code')
})
