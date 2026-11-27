import assert from 'node:assert/strict'
import test from 'node:test'

import {
  extractDesToken,
  extractEntryToken,
  extractOAuthCode,
  oauthRedirectUri,
  stripEntryToken,
} from './entryToken.js'


function fakeLocation(href) {
  const url = new URL(href)
  return {
    get href() { return url.href },
    get origin() { return url.origin },
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


test('oauth authorization code is extracted from the redirect query', () => {
  assert.equal(
    extractOAuthCode(fakeLocation('http://11.54.200.200:5175/?code=abc123')),
    'abc123'
  )
  assert.equal(
    extractOAuthCode(
      fakeLocation('http://11.54.200.200:5175/?code=xyz&state=portal#/deep/route')
    ),
    'xyz'
  )
  assert.equal(extractOAuthCode(fakeLocation('http://11.54.200.200:5175/?state=only')), '')
  assert.equal(extractOAuthCode(null), '')
})


test('oauth redirect uri is the site root of the entry origin', () => {
  assert.equal(
    oauthRedirectUri(fakeLocation('http://11.54.200.200:5175/?code=x')),
    'http://11.54.200.200:5175/'
  )
  assert.equal(oauthRedirectUri(null), '')
})


test('des token is extracted with base64 plus signs preserved', () => {
  const raw = 'e9+SraTzUfqX7qMmtgRekLi3sATWgNi5tyEXmrY+b/OYK'
  assert.equal(
    extractDesToken(fakeLocation(`http://11.54.200.200:5175/?des=${encodeURIComponent(raw)}`)),
    raw
  )
  // vue-router 中转可能把 + 变成空格，应还原
  assert.equal(
    extractDesToken(fakeLocation(`http://11.54.200.200:5175/?des=${raw.replace(/\+/g, '%20')}`)),
    raw
  )
  assert.equal(extractDesToken(fakeLocation('http://11.54.200.200:5175/?code=x')), '')
})


test('des token is recovered from the login redirect parameter', () => {
  const raw = 'e9+SraTzUfqX7qMmtgRekLi3sATWgNi5tyEXmrY+b/OYK'
  const target = `/?des=${encodeURIComponent(raw)}`
  const location = fakeLocation(`http://11.54.200.200:5175/login?redirect=${encodeURIComponent(target)}`)
  assert.equal(extractDesToken(location), raw)
})


test('strip removes the des parameter from the entry address', () => {
  const history = fakeHistory()
  const changed = stripEntryToken(
    fakeLocation('http://11.54.200.200:5175/?des=abc&from=portal'),
    history
  )

  assert.equal(changed, true)
  assert.equal(history.calls[0].url, 'http://11.54.200.200:5175/?from=portal')
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


test('strip removes the oauth code and state parameters from the redirect entry', () => {
  const history = fakeHistory()
  const changed = stripEntryToken(
    fakeLocation('http://11.54.200.200:5175/?code=one-time&state=portal&keep=1'),
    history
  )

  assert.equal(changed, true)
  assert.equal(history.calls[0].url, 'http://11.54.200.200:5175/?keep=1')
})


test('strip is a no-op without a token or a usable history', () => {
  assert.equal(stripEntryToken(fakeLocation('http://11.54.200.200:5175/?a=1'), fakeHistory()), false)
  assert.equal(stripEntryToken(fakeLocation('http://11.54.200.200:5175/?token=abc'), null), false)
  assert.equal(stripEntryToken(null, fakeHistory()), false)
})
