import assert from 'node:assert/strict'
import test from 'node:test'

import { inlineChartImages, renderChartPlaceholders } from './inlineChartImages.js'

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

test('replaces chart placeholders with the matching image resource', () => {
  const resource = {
    resource_id: 'image-a', resource_key: 'chart-image', visual_id: 'chart-a',
    label: 'trend', content_url: '/a.png'
  }
  const rendered = renderChartPlaceholders('before\n\n[[chart:chart-a]]\n\nafter', [resource])
  assert.equal(rendered.content, 'before\n\n![trend](/a.png)\n\nafter')
  assert.deepEqual([...rendered.usedResourceIds], ['image-a'])
})

test('keeps unknown chart placeholders for a later resource update', () => {
  assert.equal(renderChartPlaceholders('[[chart:missing]]', []).content, '[[chart:missing]]')
})

test('embeds static Python and report charts from the current answer', () => {
  const user = { id: 'user', type: 'user' }
  const python = { id: 'python', type: 'tool_result', data: {
    tool_name: 'execute_python', result: { visuals: [{ id: 'python-chart' }] }
  } }
  const reportChart = { id: 'report-chart', type: 'tool_result', data: {
    tool_name: 'create_report_chart', result: { visuals: [{ id: 'report-chart' }] }
  } }
  const final = { id: 'final', type: 'final' }
  const resources = ['python-chart', 'report-chart'].map(id => ({
    resource_id: id, resource_key: 'chart-image', visual_id: id,
    status: 'active', content_url: `/${id}.png`
  }))
  assert.deepEqual(
    inlineChartImages(final, [user, python, reportChart, final], resources).map(item => item.visual_id),
    ['python-chart', 'report-chart']
  )
  const packageResult = { id: 'package', type: 'tool_result', data: { tool_name: 'create_report_package' } }
  assert.deepEqual(
    inlineChartImages(final, [user, reportChart, packageResult, final], resources),
    []
  )
  assert.deepEqual(
    inlineChartImages(final, [user, python, packageResult, final], resources),
    []
  )
  assert.deepEqual(
    inlineChartImages(final, [user, reportChart, packageResult, final], resources, '[[chart:report-chart]]')
      .map(item => item.visual_id),
    ['report-chart']
  )
  assert.deepEqual(
    inlineChartImages(final, [user, reportChart, final], resources, '![图](/report-chart.png)'),
    []
  )
})
