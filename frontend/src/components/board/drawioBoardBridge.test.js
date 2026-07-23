import assert from 'node:assert/strict'
import test from 'node:test'

import { BoardSyncError, createDrawioBoardBridge } from './drawioBoardBridge.js'


const xml = '<mxfile><diagram><mxGraphModel><root /></mxGraphModel></diagram></mxfile>'


test('exports current XML only from the configured iframe and origin', async () => {
  const targetWindow = {}
  const posted = []
  const bridge = createDrawioBoardBridge({
    getTargetWindow: () => targetWindow,
    allowedOrigin: 'https://embed.diagrams.net',
    postMessage: (message, origin) => posted.push({ message: JSON.parse(message), origin }),
    timeoutMs: 100
  })

  const pending = bridge.exportCurrentXml()

  assert.equal(posted.length, 1)
  assert.deepEqual(posted[0], {
    message: { action: 'export', format: 'xml' },
    origin: 'https://embed.diagrams.net'
  })
  assert.equal(bridge.handleMessage({ source: {}, origin: 'https://embed.diagrams.net', data: JSON.stringify({ event: 'export', xml }) }), false)
  assert.equal(bridge.handleMessage({ source: targetWindow, origin: 'https://evil.example', data: JSON.stringify({ event: 'export', xml }) }), false)
  assert.equal(bridge.handleMessage({ source: targetWindow, origin: 'https://embed.diagrams.net', data: JSON.stringify({ event: 'export', xml }) }), true)

  assert.equal(await pending, xml)
})


test('blocks a send when XML synchronization times out', async () => {
  const bridge = createDrawioBoardBridge({
    getTargetWindow: () => ({}),
    allowedOrigin: 'https://embed.diagrams.net',
    postMessage: () => {},
    timeoutMs: 5
  })

  await assert.rejects(
    bridge.exportCurrentXml(),
    (error) => error instanceof BoardSyncError && error.code === 'board_sync_timeout'
  )
})


test('rejects malformed XML instead of resolving with stale state', async () => {
  const targetWindow = {}
  const bridge = createDrawioBoardBridge({
    getTargetWindow: () => targetWindow,
    allowedOrigin: 'https://embed.diagrams.net',
    postMessage: () => {},
    timeoutMs: 100
  })
  const pending = bridge.exportCurrentXml()

  bridge.handleMessage({
    source: targetWindow,
    origin: 'https://embed.diagrams.net',
    data: JSON.stringify({ event: 'export', xml: 'not xml' })
  })

  await assert.rejects(
    pending,
    (error) => error instanceof BoardSyncError && error.code === 'board_sync_invalid_xml'
  )
})


test('rejects synchronization when the editor is not ready', async () => {
  const bridge = createDrawioBoardBridge({
    getTargetWindow: () => null,
    allowedOrigin: 'https://embed.diagrams.net',
    postMessage: () => {},
  })

  await assert.rejects(
    bridge.exportCurrentXml(),
    (error) => error instanceof BoardSyncError && error.code === 'board_editor_not_ready'
  )
})
