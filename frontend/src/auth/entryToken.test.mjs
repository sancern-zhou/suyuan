import assert from 'node:assert/strict'
import test from 'node:test'

import { extractEntryToken, stripEntryToken } from './entryToken.js'


function fakeLocation(href) {
  const url = new URL(href)
  return {
    get href() { return url.href },
    get search() { return url.search },
    get hash() { return url.hash }
  }
}

function fakeHistory() {
  const calls = []
  return {
    calls,
    state: { position: 1 },
    replaceState(state, title, url) { calls.push({ state, url }) }
  }
}


test('entry token is extracted from the pre-path query', () => {
  assert.equal(
    extractEntryToken(fakeLocation('http://11.54.200.200:5175/?token=abc123')),
    'abc123'
  )
  assert.equal(
    extractEntryToken(fakeLocation('http://11.54.200.200:5175/?accessToken=xyz&other=1')),
    'xyz'
  )
  assert.equal(
    extractEntryToken(fakeLocation('http://11.54.200.200:5175/?access_token=Bearer%20abc')),
    'abc'
  )
})


test('entry token is extracted from a query embedded in the hash route', () => {
  assert.equal(
    extractEntryToken(fakeLocation('http://11.54.200.200:5175/#/some/path?token=hash-token')),
    'hash-token'
  )
  assert.equal(
    extractEntryToken(fakeLocation('http://11.54.200.200:5175/?from=portal#/deep/route?token=inner')),
    'inner'
  )
})


test('missing or blank entry tokens yield an empty string', () => {
  assert.equal(extractEntryToken(fakeLocation('http://11.54.200.200:5175/')), '')
  assert.equal(extractEntryToken(fakeLocation('http://11.54.200.200:5175/?token=%20')), '')
  assert.equal(extractEntryToken(null), '')
})


test('strip removes the token parameter from the address and keeps other params', () => {
  const history = fakeHistory()
  const changed = stripEntryToken(
    fakeLocation('http://11.54.200.200:5175/?token=abc&from=portal'),
    history
  )

  assert.equal(changed, true)
  assert.equal(history.calls.length, 1)
  assert.equal(history.calls[0].url, 'http://11.54.200.200:5175/?from=portal')
  assert.equal(history.calls[0].state, history.state)
})


test('strip cleans a hash-embedded token query and drops the bare query mark', () => {
  const history = fakeHistory()
  const changed = stripEntryToken(
    fakeLocation('http://11.54.200.200:5175/#/deep/route?token=abc&keep=1'),
    history
  )

  assert.equal(changed, true)
  assert.equal(history.calls[0].url, 'http://11.54.200.200:5175/#/deep/route?keep=1')
})


test('strip is a no-op without a token or a usable history', () => {
  assert.equal(stripEntryToken(fakeLocation('http://11.54.200.200:5175/?a=1'), fakeHistory()), false)
  assert.equal(stripEntryToken(fakeLocation('http://11.54.200.200:5175/?token=abc'), null), false)
  assert.equal(stripEntryToken(null, fakeHistory()), false)
})
