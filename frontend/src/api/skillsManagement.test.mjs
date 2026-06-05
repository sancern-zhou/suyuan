import assert from 'node:assert/strict'

import {
  getSkillDraftDetail,
  getSkillDraftsList,
  saveSkillDraftDetail
} from './skillsManagement.js'

const calls = []

globalThis.fetch = async (url, options = {}) => {
  calls.push({ url, options })
  return {
    ok: true,
    json: async () => ({ success: true })
  }
}

await getSkillDraftsList()
assert.equal(calls.at(-1).url, '/api/skills/drafts')
assert.deepEqual(calls.at(-1).options, {})

await getSkillDraftDetail('待审核技能.md')
assert.equal(calls.at(-1).url, '/api/skills/drafts/%E5%BE%85%E5%AE%A1%E6%A0%B8%E6%8A%80%E8%83%BD.md')
assert.deepEqual(calls.at(-1).options, {})

await saveSkillDraftDetail('draft', '# 草稿')
assert.equal(calls.at(-1).url, '/api/skills/drafts/draft')
assert.equal(calls.at(-1).options.method, 'PUT')
assert.equal(calls.at(-1).options.headers['Content-Type'], 'application/json')
assert.equal(calls.at(-1).options.body, JSON.stringify({ content: '# 草稿' }))

console.log('skillsManagement draft API tests passed')
