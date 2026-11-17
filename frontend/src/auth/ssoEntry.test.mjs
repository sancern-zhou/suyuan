import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeSsoEntry, ssoEntryRedirect } from './ssoEntry.js'


test('history-style sso entry is rewritten for hash routing', () => {
  assert.equal(
    ssoEntryRedirect('https://suyuan.test/sso?ticket=abc&redirect=/kb'),
    '/sso#/sso?ticket=abc&redirect=/kb'
  )
  assert.equal(
    ssoEntryRedirect('https://suyuan.test/project/sso/?ticket=abc'),
    '/project/sso#/sso?ticket=abc'
  )
})


test('sso entry rewrite ignores other routes and existing hash routes', () => {
  assert.equal(ssoEntryRedirect('https://suyuan.test/'), '')
  assert.equal(ssoEntryRedirect('https://suyuan.test/login?ticket=abc'), '')
  assert.equal(ssoEntryRedirect('https://suyuan.test/sso'), '')
  assert.equal(ssoEntryRedirect('https://suyuan.test/sso#/sso?ticket=abc'), '')
  assert.equal(ssoEntryRedirect('not a url'), '')
})


test('normalizeSsoEntry only replaces the URL when a ticket is present', () => {
  const replaced = []
  const history = { replaceState: (...args) => replaced.push(args) }

  assert.equal(
    normalizeSsoEntry({ href: 'https://suyuan.test/sso?ticket=abc' }, history),
    true
  )
  assert.deepEqual(replaced, [[null, '', '/sso#/sso?ticket=abc']])

  assert.equal(normalizeSsoEntry({ href: 'https://suyuan.test/' }, history), false)
  assert.equal(replaced.length, 1)
})
