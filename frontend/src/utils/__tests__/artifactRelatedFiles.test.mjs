import assert from 'node:assert/strict'
import {
  hasRelatedArtifactFiles,
  normalizeRelatedArtifactFiles
} from '../artifactRelatedFiles.js'

const artifact = {
  title: '自由画布测试',
  related_files: [
    { title: '自由画布测试 预览图', format: 'png', file_path: '/tmp/diagram.png' },
    { title: '自由画布测试 可编辑源文件', format: 'drawio', file_path: '/tmp/diagram.drawio' },
    { title: '自由画布测试 可编辑 SVG', format: 'drawio.svg', file_path: '/tmp/diagram.drawio.svg' }
  ]
}

const files = normalizeRelatedArtifactFiles({ artifact })

assert.equal(files.length, 3)
assert.deepEqual(files.map(file => file.format), ['png', 'drawio', 'drawio.svg'])
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
