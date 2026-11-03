import assert from 'node:assert/strict'
import test from 'node:test'

import { createOAuthApi } from './oauthApi.js'


test('exchangeCode calls the gateway exchange endpoint and returns token fields', async () => {
  const seen = []
  const api = createOAuthApi({
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async (url) => {
      seen.push(url)
      return new Response(JSON.stringify({
        accessToken: 'access-1',
        refreshToken: 'refresh-1',
        expiresIn: 3600,
        tokenType: 'bearer'
      }), { status: 200 })
    }
  })

  const result = await api.exchangeCode('one-time-code', 'http://11.54.200.200:5175/')

  assert.equal(result.accessToken, 'access-1')
  assert.equal(result.refreshToken, 'refresh-1')
  assert.equal(result.expiresIn, 3600)
  assert.equal(
    seen[0],
    '/api/suyuan/auth/oauth/exchange?' +
      new URLSearchParams({ code: 'one-time-code', redirectUri: 'http://11.54.200.200:5175/' }).toString()
  )
})


test('exchange failures surface the backend detail', async () => {
  const api = createOAuthApi({
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async () => new Response(
      JSON.stringify({ detail: 'oauth_not_configured' }),
      { status: 503 }
    )
  })

  await assert.rejects(
    () => api.exchangeCode('code', 'http://11.54.200.200:5175/'),
    /oauth_not_configured/
  )
})


test('an exchange response without an access token is rejected', async () => {
  const api = createOAuthApi({
    apiBaseUrl: '/api/suyuan',
    fetchImpl: async () => new Response(JSON.stringify({ accessToken: '' }), { status: 200 })
  })

  await assert.rejects(
    () => api.exchangeCode('code', 'http://11.54.200.200:5175/'),
    /未返回访问令牌/
  )
})
