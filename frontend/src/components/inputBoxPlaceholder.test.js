import assert from 'node:assert/strict'
import test from 'node:test'

import { withComposerShortcutGuide } from './inputBoxPlaceholder.js'

test('appends slash skill and at file guidance to a mode-specific placeholder', () => {
  assert.equal(
    withComposerShortcutGuide('描述您想分析的气象问题...'),
    '描述您想分析的气象问题，使用 / 选择技能，@ 引用对话文件...'
  )
})

test('uses the general question prompt when the base placeholder is empty', () => {
  assert.equal(
    withComposerShortcutGuide(''),
    '输入您的问题，使用 / 选择技能，@ 引用对话文件...'
  )
})
