import assert from 'node:assert/strict'
import test from 'node:test'

import { exchangeSsoTicket, normalizeSsoExchange } from './sso.js'


function fakeFetch(status, body) {
  const calls = []
  const fetchImpl = async (url, options) => {
    calls.push({ url, options })
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body
    }
  }
  return { fetchImpl, calls }
}


test('normalizeSsoExchange accepts a complete session payload', () => {
  const session = normalizeSsoExchange(
    {
      token: ' local-token ',
      sysCode: 'SUYUAN',
      user: { id: 'u1', userName: 'zhangsan', roleCodes: ['viewer'] }
    },
    'SUYUAN'
  )

  assert.equal(session.token, 'local-token')
  assert.equal(session.sysCode, 'SUYUAN')
  assert.equal(session.user.name, 'zhangsan')
  assert.deepEqual(session.user.roleCodes, ['viewer'])
})


test('normalizeSsoExchange fills defaults for optional fields', () => {
  const session = normalizeSsoExchange(
    { token: 't', user: { id: 'u1', userName: 'zhangsan', name: '张三' } },
    'SUYUAN'
  )

  assert.equal(session.sysCode, 'SUYUAN')
  assert.deepEqual(session.user.roleCodes, [])
  assert.equal(session.user.name, '张三')
})


test('normalizeSsoExchange rejects incomplete payloads', () => {
  assert.throws(() => normalizeSsoExchange(null, 'SUYUAN'), /外部登录校验失败/)
  assert.throws(() => normalizeSsoExchange({ user: { id: 'u1', userName: 'a' } }), /会话令牌/)
  assert.throws(() => normalizeSsoExchange({ token: 't' }), /用户信息/)
  assert.throws(
    () => normalizeSsoExchange({ token: 't', user: { id: '', userName: 'a' } }),
    /用户信息/
  )
})


test('exchangeSsoTicket posts the ticket to the exchange endpoint', async () => {
  const { fetchImpl, calls } = fakeFetch(200, {
    token: 'token-1',
    sysCode: 'SUYUAN',
    user: { id: 'u1', userName: 'zhangsan' }
  })

  const body = await exchangeSsoTicket({
    ticket: ' ticket-1 ',
    fetchImpl,
    apiBaseUrl: 'https://suyuan.test/api/suyuan/'
  })

  assert.equal(body.token, 'token-1')
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, 'https://suyuan.test/api/suyuan/auth/sso/exchange')
  assert.equal(calls[0].options.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].options.body), { ticket: 'ticket-1' })
})


test('exchangeSsoTicket reports server rejection details', async () => {
  const { fetchImpl } = fakeFetch(401, { detail: 'sso_ticket_expired' })

  await assert.rejects(
    exchangeSsoTicket({ ticket: 'ticket-1', fetchImpl, apiBaseUrl: '/api/suyuan' }),
    /sso_ticket_expired/
  )
})


test('exchangeSsoTicket requires a ticket before calling the API', async () => {
  const { fetchImpl, calls } = fakeFetch(200, {})

  await assert.rejects(
    exchangeSsoTicket({ ticket: '   ', fetchImpl, apiBaseUrl: '/api/suyuan' }),
    /缺少外部登录票据/
  )
  assert.equal(calls.length, 0)
})
