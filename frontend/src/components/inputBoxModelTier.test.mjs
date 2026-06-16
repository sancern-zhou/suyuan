import assert from 'node:assert/strict'
import {
  getEffectiveModelTier,
  shouldShowModelTierSelector
} from './inputBoxModelTier.js'

assert.equal(
  shouldShowModelTierSelector('assistant'),
  true,
  'assistant mode should allow frontend model selection'
)

assert.equal(
  shouldShowModelTierSelector('chart'),
  false,
  'chart mode should not show frontend model selection'
)

assert.equal(
  shouldShowModelTierSelector('social'),
  false,
  'social mode should not show frontend model selection'
)

assert.equal(
  getEffectiveModelTier('pro', 'chart'),
  'auto',
  'chart mode should ignore a stored pro model tier'
)

assert.equal(
  getEffectiveModelTier('flash', 'social'),
  'auto',
  'social mode should ignore a stored flash model tier'
)

assert.equal(
  getEffectiveModelTier('pro', 'assistant'),
  'pro',
  'assistant mode should keep the selected model tier'
)

console.log('inputBoxModelTier tests passed')
