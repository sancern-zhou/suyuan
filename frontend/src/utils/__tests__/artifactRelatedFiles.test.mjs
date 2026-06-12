import assert from 'node:assert/strict'
import {
  buildArtifactDownloadPayload,
  hasRelatedArtifactFiles,
  normalizeArtifactUrl,
  normalizeRelatedArtifactFiles
} from '../artifactRelatedFiles.js'

const artifact = {
  title: '自由画布测试',
  related_files: [
    { title: '自由画布测试 预览图', format: 'png', file_path: '/tmp/diagram.png' },
    { title: '自由画布测试 可编辑源文件', format: 'drawio', file_path: '/tmp/diagram.drawio' },
    { title: '自由画布测试 可编辑 SVG', format: 'drawio.svg', file_path: '/tmp/diagram.drawio.svg' },
    { title: '自由画布测试 Source JSON', format: 'json', file_path: '/tmp/diagram.source.json' },
    { title: '自由画布测试 HTML', format: 'html', file_path: '/tmp/index.html' }
  ]
}

const files = normalizeRelatedArtifactFiles({ artifact })

assert.equal(files.length, 3)
assert.deepEqual(files.map(file => file.format), ['png', 'drawio', 'drawio_svg'])
assert.equal(files[1].downloadLabel, '自由画布测试 可编辑源文件')

const refsOnly = normalizeRelatedArtifactFiles({
  refs: {
    artifacts: [
      { title: '源文件', format: 'drawio', file_path: '/tmp/source.drawio' }
    ]
  }
})

assert.equal(refsOnly.length, 1)
assert.equal(refsOnly[0].format, 'drawio')

const singleArtifact = normalizeRelatedArtifactFiles({
  artifact: {
    kind: 'editable_diagram',
    format: 'drawio',
    file_path: '/tmp/standalone.drawio',
    file_name: 'standalone.drawio'
  }
})

assert.equal(singleArtifact.length, 1)
assert.equal(singleArtifact[0].format, 'drawio')
assert.equal(singleArtifact[0].downloadLabel, 'standalone.drawio')

const payload = buildArtifactDownloadPayload({
  result: {
    data: {
      title: '分层架构图',
      artifact: {
        title: '分层架构图 SVG 预览',
        format: 'svg',
        file_path: '/tmp/diagram.drawio.svg'
      },
      related_files: [
        { title: '分层架构图 可编辑源文件', format: 'drawio', file_path: '/tmp/diagram.drawio' },
        { title: '分层架构图 SVG 预览', format: 'drawio_svg', file_path: '/tmp/diagram.drawio.svg' }
      ]
    }
  },
  latestVisualization: {
    title: '分层架构图',
    format: 'svg',
    file_path: '/tmp/diagram.drawio.svg'
  }
})
const payloadFiles = normalizeRelatedArtifactFiles({ artifact: payload, refs: payload.refs })

assert.deepEqual(payloadFiles.map(file => file.format), ['drawio', 'drawio_svg'])

assert.equal(
  normalizeArtifactUrl('http://219.135.180.51:56041/api/html-artifacts/puyang-smart-env-architecture/assets/diagram.drawio.svg'),
  '/api/html-artifacts/puyang-smart-env-architecture/assets/diagram.drawio.svg'
)

assert.equal(
  normalizeArtifactUrl('https://example.com/api/html-artifacts/puyang-smart-env-architecture/assets/diagram.png'),
  '/api/html-artifacts/puyang-smart-env-architecture/assets/diagram.png'
)

assert.equal(
  hasRelatedArtifactFiles({
    refs: {
      artifacts: [
        { title: '源文件', format: 'drawio', file_path: '/tmp/source.drawio' }
      ]
    }
  }),
  true
)
