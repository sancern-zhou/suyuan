import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(__dirname, './SkillsManagementView.vue'), 'utf8')

assert.match(source, /activeSkillType\s*=\s*ref\('official'\)/, 'Skills page should track official vs draft list mode')
assert.match(source, /待审核草稿/, 'Skills page should expose a draft review tab or label')
assert.match(source, /getSkillDraftsList/, 'Draft mode should load draft skills through the draft list API')
assert.match(source, /getSkillDraftDetail/, 'Draft detail should use the draft detail API')
assert.match(source, /saveSkillDraftDetail/, 'Draft save should use the draft save API')
assert.match(source, /currentSkill\?\.is_draft/, 'Detail view should visibly mark draft skills as draft content')

console.log('SkillsManagementView draft review tests passed')
