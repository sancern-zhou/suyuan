import assert from 'node:assert/strict'
import { convertStreamingAnswerToThoughtIfToolPlanning } from './reactStoreStreaming.js'

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

console.log('reactStoreStreaming tests passed')
