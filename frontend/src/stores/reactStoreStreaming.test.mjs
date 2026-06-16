import assert from 'node:assert/strict'
import {
  convertStreamingAnswerToThoughtIfToolPlanning,
  freezeActiveAssistantOutput
} from './reactStoreStreaming.js'

const state = {
  streamingAnswerMessageId: 'msg_streaming_final',
  finalAnswer: '最终回复第一遍',
  _forceRenderCount: 0,
  messages: [
    { id: 'msg_user', type: 'user', content: '生成报告' },
    {
      id: 'msg_streaming_final',
      type: 'final',
      content: '最终回复第一遍',
      streaming: true,
      data: { timestamp: '2026-06-02T13:48:37Z' }
    }
  ]
}

const converted = convertStreamingAnswerToThoughtIfToolPlanning(state)

assert.equal(converted, true)
assert.equal(state.streamingAnswerMessageId, null)
assert.equal(state.finalAnswer, '')
assert.equal(state._forceRenderCount, 1)
assert.equal(state.messages[1].type, 'thought')
assert.equal(state.messages[1].streaming, false)
assert.equal(state.messages[1].content, '最终回复第一遍')
assert.equal(state.messages[1].data.converted_from, 'pre_tool_streaming_text')

const pausedState = {
  streamingAnswerMessageId: null,
  finalAnswer: '',
  _forceRenderCount: 0,
  messages: [
    { id: 'msg_user', type: 'user', content: '分析污染过程' },
    { id: 'msg_thought', type: 'thought', content: '正在判断污染时段' },
    { id: 'msg_tool', type: 'tool_result', content: '已获取监测数据' }
  ]
}

const frozen = freezeActiveAssistantOutput(pausedState, {
  reason: 'paused',
  content: '已暂停当前分析，保留已产生的分析过程。'
})

assert.equal(frozen, true)
assert.equal(pausedState.messages.length, 4)
assert.equal(pausedState.messages[3].type, 'final')
assert.equal(pausedState.messages[3].content, '已暂停当前分析，保留已产生的分析过程。')
assert.equal(pausedState.messages[3].data.frozen_from, 'paused')
assert.equal(pausedState._forceRenderCount, 1)

const streamingState = {
  streamingAnswerMessageId: 'msg_stream',
  finalAnswer: '已有流式回复',
  _forceRenderCount: 0,
  messages: [
    { id: 'msg_user', type: 'user', content: '写总结' },
    { id: 'msg_stream', type: 'final', content: '已有流式回复', streaming: true }
  ]
}

const frozenStreaming = freezeActiveAssistantOutput(streamingState, { reason: 'queued_input' })

assert.equal(frozenStreaming, true)
assert.equal(streamingState.streamingAnswerMessageId, null)
assert.equal(streamingState.messages.length, 2)
assert.equal(streamingState.messages[1].streaming, false)
assert.equal(streamingState.messages[1].content, '已有流式回复')
assert.equal(streamingState.messages[1].data.frozen_from, 'queued_input')

console.log('reactStoreStreaming tests passed')
