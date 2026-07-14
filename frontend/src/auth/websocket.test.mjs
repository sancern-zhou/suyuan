import assert from 'node:assert/strict'
import test from 'node:test'

import { connectScheduledTaskWebSocket } from './websocket.js'


test('scheduled-task sockets use wss, gateway path, and a fresh one-time ticket', async () => {
  const issued = ['ticket-one', 'ticket-two']
  const requests = []
  const urls = []
  const fetchImpl = async (url, options) => {
    requests.push([url, options])
    return new Response(JSON.stringify({ ticket: issued.shift(), expires_in: 30 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  }
  class FakeWebSocket {
    constructor(url) { this.url = url; urls.push(url) }
  }

  await connectScheduledTaskWebSocket({
    authFetch: fetchImpl,
    WebSocketImpl: FakeWebSocket,
    location: { protocol: 'https:', host: 'platform.example' },
    apiBaseUrl: '/api/suyuan'
  })
  await connectScheduledTaskWebSocket({
    authFetch: fetchImpl,
    WebSocketImpl: FakeWebSocket,
    location: { protocol: 'https:', host: 'platform.example' },
    apiBaseUrl: '/api/suyuan'
  })

  assert.deepEqual(requests.map(item => item[0]), [
    '/api/auth/ws-ticket',
    '/api/auth/ws-ticket'
  ])
  assert.deepEqual(urls, [
    'wss://platform.example/api/suyuan/ws/scheduled-tasks?ticket=ticket-one',
    'wss://platform.example/api/suyuan/ws/scheduled-tasks?ticket=ticket-two'
  ])
  assert.equal(urls.some(url => url.includes('company-token')), false)
})


test('http pages select ws protocol', async () => {
  class FakeWebSocket { constructor(url) { this.url = url } }
  const socket = await connectScheduledTaskWebSocket({
    authFetch: async () => new Response(JSON.stringify({ ticket: 'ticket' })),
    WebSocketImpl: FakeWebSocket,
    location: { protocol: 'http:', host: 'localhost:5174' },
    apiBaseUrl: '/api/suyuan'
  })
  assert.equal(socket.url, 'ws://localhost:5174/api/suyuan/ws/scheduled-tasks?ticket=ticket')
})
