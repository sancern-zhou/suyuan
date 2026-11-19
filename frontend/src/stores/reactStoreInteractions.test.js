import test from 'node:test'
import assert from 'node:assert/strict'

import { buildQuestionResumeOptions } from './reactStoreInteractions.js'

const interaction = { interaction_id: 'it-1', mode: 'assistant' }

test('full-page resolution keeps the legacy behavior: no preserveCurrentMode', () => {
  // 全页工作区没有外部目标状态，续跑参数与历史行为完全一致。
  const options = buildQuestionResumeOptions({
    resolution: { resume_query: '继续' },
    interaction,
    interactionState: { mode: 'assistant' },
    currentMode: 'data_query',
    externalTarget: false
  })

  assert.equal(options.agentMode, 'assistant')
  assert.equal(options.preserveCurrentMode, false)
  assert.equal(options.synthetic, true)
  assert.equal(options.queuedAlreadyShown, true)
  assert.equal(options.syntheticMeta.source, 'structured_question_resume')
  assert.equal(options.syntheticMeta.interaction_id, 'it-1')
})

test('floating-window resolution resumes in place without hijacking the global mode', () => {
  // 浮窗回答：不切换全局 currentMode，原地续跑 assistant 会话。
  const options = buildQuestionResumeOptions({
    resolution: { resume_query: '继续' },
    interaction,
    interactionState: { mode: 'assistant' },
    currentMode: 'data_query',
    externalTarget: true
  })

  assert.equal(options.agentMode, 'assistant')
  assert.equal(options.preserveCurrentMode, true)
})

test('agentMode falls back through resolution, interaction, state then global mode', () => {
  const base = { interaction, interactionState: { mode: 'assistant' }, externalTarget: true }
  assert.equal(buildQuestionResumeOptions({ ...base, resolution: { mode: 'expert' } }).agentMode, 'expert')
  assert.equal(buildQuestionResumeOptions({ ...base, resolution: {} }).agentMode, 'assistant')
  // interaction.mode 缺失时取会话状态记录的模式。
  assert.equal(
    buildQuestionResumeOptions({ ...base, resolution: {}, interaction: { interaction_id: 'it-1' } }).agentMode,
    'assistant'
  )
  // 全链缺失时才回落全局当前模式。
  assert.equal(
    buildQuestionResumeOptions({
      ...base,
      resolution: {},
      interaction: { interaction_id: 'it-1' },
      interactionState: {},
      currentMode: 'expert'
    }).agentMode,
    'expert'
  )
})
