import assert from 'node:assert/strict'
import { getPendingSteeringDisplay } from './inputBoxPendingSteering.js'

assert.equal(
  getPendingSteeringDisplay([]).text,
  '',
  'empty pending steering inputs should render no text'
)

assert.deepEqual(
  getPendingSteeringDisplay([
    { id: 's1', content: '补充考虑昨天数据' }
  ]),
  {
    text: '补充考虑昨天数据',
    extraCount: 0
  },
  'single pending steering input should show its content'
)

assert.deepEqual(
  getPendingSteeringDisplay([
    { id: 's1', content: '第一条追加' },
    { id: 's2', content: '第二条追加' },
    { id: 's3', content: '最新追加问题' }
  ]),
  {
    text: '最新追加问题',
    extraCount: 2
  },
  'multiple pending steering inputs should show the latest content and count older ones'
)

console.log('inputBoxPendingSteering tests passed')
