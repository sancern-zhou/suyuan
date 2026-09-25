import assert from 'node:assert/strict'
import test from 'node:test'

import { inlineChartImages } from './inlineChartImages.js'

test('only embeds image renditions produced by the final response tool calls', () => {
  const user = { id: 'user', type: 'user' }
  const tool = { id: 'tool', type: 'tool_result', data: {
    tool_name: 'execute_echarts_python', result: { visuals: [{ id: 'chart-a' }] }
  } }
  const final = { id: 'final', type: 'final' }
  const resources = [
    { resource_id: 'image-a', resource_key: 'chart-image', visual_id: 'chart-a', status: 'active', content_url: '/a.png' },
    { resource_id: 'image-b', resource_key: 'chart-image', visual_id: 'chart-b', status: 'active', content_url: '/b.png' }
  ]
  assert.deepEqual(inlineChartImages(final, [user, tool, final], resources).map(item => item.resource_id), ['image-a'])
  assert.deepEqual(inlineChartImages(final, [user, final], resources), [])
})
