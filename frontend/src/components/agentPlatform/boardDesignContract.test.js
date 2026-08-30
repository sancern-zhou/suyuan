import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const storeSource = readFileSync(new URL('../../stores/reactStore.js', import.meta.url), 'utf8')

test('board state keeps the shared design contract across tool results', () => {
  assert.match(storeSource, /designSpec:\s*\{\}/)
  assert.match(storeSource, /themeTokens:\s*\{\}/)
  assert.match(storeSource, /structuralDigest:\s*\{\}/)
  assert.match(storeSource, /payload\.design_spec\s*\|\|\s*payload\.designSpec/)
  assert.match(storeSource, /payload\.quality_report\?\.design_spec/)
  assert.match(storeSource, /payload\.quality_report\?\.theme_tokens/)
})

test('board context sends design and theme metadata in compact and xml forms', () => {
  const designMatches = storeSource.match(/design_spec:\s*board\.designSpec\s*\|\|\s*\{\}/g) || []
  const themeMatches = storeSource.match(/theme_tokens:\s*board\.themeTokens\s*\|\|\s*\{\}/g) || []

  assert.equal(designMatches.length, 2)
  assert.equal(themeMatches.length, 2)
})
