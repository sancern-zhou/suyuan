import assert from 'node:assert/strict'
import {
  getExecutingProcessMessages,
  getUnifiedProcessMessages
} from './messageProcessGrouping.js'

const messages = [
  { id: 'u1', type: 'user', content: '开始分析' },
  { id: 't1', type: 'thought', content: '读取需求' },
  { id: 'tool1', type: 'tool_use', content: 'Tool Use: query' },
  {
    id: 's1',
    type: 'user',
    content: '补充考虑昨天数据',
    steering: true,
    steeringStatus: 'applied'
  },
  { id: 'r1', type: 'tool_result', content: 'Tool Result: done' },
  { id: 't2', type: 'thought', content: '整理结论' },
  { id: 'f1', type: 'final', content: '分析完成' }
]

assert.deepEqual(
  getExecutingProcessMessages(messages.slice(0, -1)).map(message => message.id),
  ['t1', 'tool1', 'r1', 't2'],
  'applied steering user should not split live process messages'
)

assert.deepEqual(
  getUnifiedProcessMessages(messages[6], messages).map(message => message.id),
  ['t1', 'tool1', 'r1', 't2'],
  'applied steering user should not split final process messages'
)

console.log('messageProcessGrouping tests passed')
