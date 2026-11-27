import test from 'node:test'
import assert from 'node:assert/strict'
import { chartReferenceIds } from './chartReferencePattern.js'
import { indexInlineChartResources } from './inlineChartResources.js'

const specId = 'ab'.repeat(16)
const imageId = 'cd'.repeat(16)
const fileImageId = 'ef'.repeat(16)
const chart = id => `[[chart:${id}]]`
const resource = (resource_id, resource_key, renderer, scope = 'sessions', owner = 'session-1') => ({
  resource_id, resource_key, renderer, status: 'active', group_id: 'same-group',
  content_url: `/api/suyuan/${scope}/${owner}/resources/${resource_id}/content?preview_ticket=granted`
})

test('only recognizes the exact lowercase hex contract in occurrence order', () => {
  const content = `分析 ${chart(imageId)} 然后 ${chart(specId)}。 ${chart(imageId)}\n` +
    [chart('chart_1'), chart('generic_PM2.5'), chart('图表 路径.png'), chart(specId.toUpperCase()),
      chart(specId.slice(1)), chart(specId + '0'), chart(` ${specId}`), `![图](/chart/${specId})`].join('\n')
  assert.deepEqual(chartReferenceIds(content), [imageId, specId, imageId])
})

test('leaves inline, fenced, nested, and indented code literal', () => {
  const source = [
    '`' + chart(specId) + '`',
    '``code ` ' + chart(specId) + '``',
    '\\' + chart(specId),
    '```text\n' + chart(specId) + '\n```',
    '> ~~~~ text\n> ' + chart(specId) + '\n> ~~~~',
    '- ```\n  ' + chart(specId) + '\n  ```',
    'End of list.',
    '    ' + chart(specId),
    'before **' + chart(imageId) + '** after',
    '```\n' + chart(specId)
  ].join('\n\n')
  assert.deepEqual(chartReferenceIds(source), [imageId])
})

test('indexes exact spec and static members without substituting a sibling or alias', () => {
  const spec = resource(specId, 'chart-spec', 'chart')
  const image = resource(imageId, 'chart-image', 'image')
  const fileImage = resource(fileImageId, 'primary:png', 'image')
  const map = indexInlineChartResources([spec, image, fileImage], 'sessions', 'session-1')
  assert.deepEqual([...map.values()].map(item => item.kind), ['spec', 'image', 'image'])
  assert.equal(map.get(specId).resource, spec)
  assert.equal(map.get(imageId).resource, image)
  assert.equal(map.get(fileImageId).resource, fileImage)
  assert.equal(map.get(specId).url, `/api/sessions/session-1/resources/${specId}/content?preview_ticket=granted`)
  assert.equal(map.has('same-group'), false)
})

test('rejects inactive, non-image, unavailable, and wrong-scope resources', () => {
  const spec = resource(specId, 'chart-spec', 'chart')
  const image = resource(imageId, 'chart-image', 'image')
  const file = resource(fileImageId, 'primary:pdf', 'pdf')
  const candidates = [file, { ...spec, status: 'deleted' }, { ...spec, interactive: false },
    { ...image, content_url: undefined }, { ...image, content_url: spec.content_url },
    { ...image, content_url: `https://example.com${image.content_url}` },
    resource(specId, 'chart-spec', 'chart', 'sessions', 'another-session')]
  assert.equal(indexInlineChartResources(candidates, 'sessions', 'session-1').size, 0)
})

test('share uses only its own snapshot content URLs and supports the standalone gateway base', () => {
  const spec = resource(specId, 'chart-spec', 'chart', 'shared-conversations', 'share-1')
  const standalone = '/suyuan/api/suyuan'
  spec.content_url = `/suyuan${spec.content_url}`
  const map = indexInlineChartResources([spec, resource(imageId, 'chart-image', 'image')],
    'shared-conversations', 'share-1', standalone)
  assert.equal(map.size, 1)
  assert.equal(map.get(specId).url, `/api/shared-conversations/share-1/resources/${specId}/content?preview_ticket=granted`)
})
