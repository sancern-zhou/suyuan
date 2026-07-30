import assert from 'node:assert/strict'
import test from 'node:test'

import * as commandPalette from './inputBoxCommandPalette.js'

const {
  buildComposerPayload,
  findComposerTrigger,
  normalizeConversationResources,
  normalizeSkills,
  shouldClearAcceptedComposer
} = commandPalette

test('detects slash and at triggers only at token boundaries', () => {
  assert.deepEqual(findComposerTrigger('请使用 /趋势', 7), {
    type: 'skill',
    symbol: '/',
    start: 4,
    search: '趋势'
  })
  assert.deepEqual(findComposerTrigger('分析 @报告.docx', 12), {
    type: 'file',
    symbol: '@',
    start: 3,
    search: '报告.docx'
  })
  assert.equal(findComposerTrigger('user@example.com', 16), null)
})

test('normalizes skills and filters disabled drafts', () => {
  assert.deepEqual(normalizeSkills({
    data: {
      skills: [
        { id: 'trend', name: '趋势分析', description: '比较趋势', enabled: true },
        { id: 'draft', name: '草稿', is_draft: true }
      ]
    }
  }), [
    { id: 'trend', name: '趋势分析', description: '比较趋势', aliases: [], compatible: true, missingTools: [] }
  ])
})

test('normalizes active file and artifact resources for the at menu', () => {
  const resources = normalizeConversationResources({
    resources: [
      { ref_id: 'upload-1', kind: 'file', label: '数据.xlsx', status: 'active', role: 'attachment', metadata: { source: 'user_upload' } },
      { ref_id: 'report-1', kind: 'artifact', label: '报告.docx', status: 'active', role: 'report', tool_name: 'generate_report' },
      { ref_id: 'old-1', kind: 'file', label: '旧文件.txt', status: 'superseded' },
      { ref_id: 'url-1', kind: 'url', label: '网页', status: 'active' }
    ]
  })

  assert.deepEqual(resources.map(item => [item.id, item.group]), [
    ['upload-1', '用户上传'],
    ['report-1', 'Agent 生成']
  ])
})

test('builds structured context refs and safe message attachments', () => {
  const payload = buildComposerPayload({
    query: '分析数据',
    skill: { id: 'trend', name: '趋势分析' },
    files: [
      {
        id: 'upload-1',
        fileId: 'file-1',
        name: '验收规范.md',
        type: 'file',
        mimeType: 'text/markdown',
        url: '/api/upload/file-1',
        pinnedPolicy: true
      },
      {
        id: 'upload-2',
        fileId: 'file-2',
        name: '本轮数据.csv',
        type: 'file',
        mimeType: 'text/csv',
        url: '/api/upload/file-2'
      }
    ],
    agentMode: 'query',
    modelTier: 'auto',
    knowledgeBaseIds: ['kb-1']
  })

  assert.deepEqual(payload, {
    query: '分析数据',
    skillIds: ['trend'],
    activeContexts: [
      { type: 'skill', id: 'trend', label: '趋势分析' },
      { type: 'fixed_policy', id: 'upload-1', label: '验收规范.md' }
    ],
    contextRefs: [{ type: 'conversation_file', resource_id: 'upload-2', display_name: '本轮数据.csv' }],
    messageAttachments: [{
      file_id: 'file-2',
      name: '本轮数据.csv',
      type: 'file',
      mime_type: 'text/csv',
      url: '/api/upload/file-2'
    }],
    agentMode: 'query',
    modelTier: 'auto',
    knowledgeBaseIds: ['kb-1']
  })
  assert.equal('attachments' in payload, false)
})

test('preserves server active contexts while authoritative restore state is unknown', () => {
  const payload = buildComposerPayload({
    query: '继续分析',
    skill: { id: 'stale-local-skill', name: '本地旧选择' },
    files: [],
    activeContextsLoaded: false,
    activeContextsDirty: false
  })

  assert.equal(payload.activeContexts, null)
  assert.deepEqual(payload.skillIds, [])
})

test('sends an explicit replacement after the user edits unknown active contexts', () => {
  const payload = buildComposerPayload({
    query: '继续分析',
    skill: { id: 'trend', name: '趋势分析' },
    files: [],
    activeContextsLoaded: false,
    activeContextsDirty: true
  })

  assert.deepEqual(payload.activeContexts, [
    { type: 'skill', id: 'trend', label: '趋势分析' }
  ])
})

test('does not apply an in-flight restore after the active contexts were edited', () => {
  assert.equal(commandPalette.shouldApplyActiveContextRestore?.({
    restoreEditVersion: 2,
    currentEditVersion: 3,
    dirty: true
  }), false)
})

test('accepts an explicit replacement independently from unrelated composer edits', () => {
  assert.deepEqual(commandPalette.resolveAcceptedActiveContextState?.({
    explicit: true,
    sentSignature: 'skill:trend',
    currentSignature: 'skill:trend',
    dirty: true,
    currentEditVersion: 4
  }), {
    loaded: true,
    dirty: false,
    editVersion: 5
  })
})

test('only clears the composer if the accepted draft is still current', () => {
  const sent = { query: '分析', skillId: 'trend', fileIds: ['f1'] }
  assert.equal(shouldClearAcceptedComposer(sent, { ...sent }), true)
  assert.equal(shouldClearAcceptedComposer(sent, { ...sent, query: '分析更多' }), false)
  assert.equal(shouldClearAcceptedComposer(sent, { ...sent, fileIds: ['f1', 'f2'] }), false)
})
