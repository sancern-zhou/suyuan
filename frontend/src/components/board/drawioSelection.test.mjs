import assert from 'node:assert/strict'
import {
  getDrawioSelectionPayload,
  getDrawioSelectionPayloadFromExport,
  parseDrawioSelectedCells
} from './drawioSelection.js'

const xml = `
<mxfile>
  <diagram id="page-1">
    <mxGraphModel>
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="service_a" value="用户服务" style="rounded=1;fillColor=#dae8fc;" vertex="1" parent="1">
          <mxGeometry x="120" y="80" width="140" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="edge_1" value="调用" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="service_a" target="service_b" parent="1">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
`

const selected = parseDrawioSelectedCells(xml, ['service_a'])

assert.equal(selected.length, 1)
assert.equal(selected[0].id, 'service_a')
assert.equal(selected[0].value, '用户服务')
assert.equal(selected[0].vertex, true)
assert.equal(selected[0].edge, false)
assert.equal(selected[0].parent, '1')
assert.deepEqual(selected[0].geometry, {
  x: 120,
  y: 80,
  width: 140,
  height: 60
})
assert.match(selected[0].xml, /<mxCell id="service_a"/)

const selectedEdge = parseDrawioSelectedCells(xml, [{ id: 'edge_1' }])

assert.equal(selectedEdge.length, 1)
assert.equal(selectedEdge[0].edge, true)
assert.equal(selectedEdge[0].vertex, false)
assert.equal(selectedEdge[0].source, 'service_a')
assert.equal(selectedEdge[0].target, 'service_b')

const unknown = parseDrawioSelectedCells(xml, ['missing'])

assert.deepEqual(unknown, [{ id: 'missing' }])

const singleObject = parseDrawioSelectedCells(xml, { id: 'service_a' })

assert.equal(singleObject.length, 1)
assert.equal(singleObject[0].id, 'service_a')

assert.deepEqual(getDrawioSelectionPayload({ selectedIds: ['service_a'] }), ['service_a'])
assert.deepEqual(getDrawioSelectionPayload({ cellIds: ['edge_1'] }), ['edge_1'])
assert.deepEqual(getDrawioSelectionPayload({ cell: { id: 'service_a' } }), { id: 'service_a' })

const selectionExport = {
  event: 'export',
  format: 'json',
  data: {
    pages: [
      {
        id: 'page-1',
        cells: [
          { id: '1', type: 'layer' },
          { id: 'service_a', type: 'node', label: '用户服务' },
          { id: 'edge_1', type: 'edge', label: '调用' }
        ]
      }
    ]
  }
}

assert.deepEqual(getDrawioSelectionPayloadFromExport(selectionExport), ['service_a', 'edge_1'])
assert.deepEqual(getDrawioSelectionPayloadFromExport({ event: 'export', format: 'json', data: '{}' }), [])

console.log('draw.io selection parsing checks passed')
