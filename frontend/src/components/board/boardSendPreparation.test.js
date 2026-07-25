import assert from 'node:assert/strict'
import test from 'node:test'

import { prepareBoardForSend } from './boardSendPreparation.js'


test('synchronizes XML and commits a manual version before returning board context', async () => {
  const calls = []
  const board = {
    activeBoardId: 'board-1',
    currentVersionId: 'version-1',
    currentXml: '<mxfile>old</mxfile>',
    revision: 1,
    selectedCells: [{ id: 'node-1' }]
  }

  const result = await prepareBoardForSend({
    board,
    getSourceVersionId: () => 'version-1',
    exportXml: async () => {
      calls.push('sync')
      return '<mxfile>latest</mxfile>'
    },
    updateXml: (xml) => {
      calls.push(`update:${xml}`)
      board.currentXml = xml
    },
    commitManual: async (payload) => {
      calls.push(`commit:${payload.base_revision}:${payload.source_version_id}:${payload.xml}`)
      return {
        board_id: 'board-1',
        current_version_id: 'version-2',
        revision: 2,
        version: { version_id: 'version-2', xml_sha256: 'hash-2' }
      }
    },
    onCommitted: ({ xml }) => calls.push(`confirmed:${xml}`)
  })

  assert.deepEqual(calls, [
    'sync',
    'commit:1:version-1:<mxfile>latest</mxfile>',
    'update:<mxfile>latest</mxfile>',
    'confirmed:<mxfile>latest</mxfile>'
  ])
  assert.deepEqual(result.context, {
    board_id: 'board-1',
    version_id: 'version-2',
    revision: 2,
    selected_cells: [{ id: 'node-1' }]
  })
  assert.equal(board.revision, 2)
  assert.equal(board.currentVersionId, 'version-2')
  assert.equal(board.currentVersionSha256, 'hash-2')
})


test('does not commit when synchronization fails', async () => {
  let commitCalls = 0
  await assert.rejects(
    prepareBoardForSend({
      board: { activeBoardId: 'board-1', currentXml: '<mxfile>old</mxfile>', revision: 1 },
      exportXml: async () => { throw Object.assign(new Error('timeout'), { code: 'board_sync_timeout' }) },
      updateXml: () => {},
      commitManual: async () => { commitCalls += 1 }
    }),
    (error) => error.code === 'board_sync_timeout'
  )
  assert.equal(commitCalls, 0)
})


test('does not replace current XML when the manual version commit fails', async () => {
  const board = { activeBoardId: 'board-1', currentXml: '<mxfile>current</mxfile>', revision: 1 }
  let updateCalls = 0
  let committedCalls = 0

  await assert.rejects(
    prepareBoardForSend({
      board,
      exportXml: async () => '<mxfile>working</mxfile>',
      updateXml: () => { updateCalls += 1 },
      commitManual: async () => { throw Object.assign(new Error('conflict'), { code: 'board_version_conflict' }) },
      onCommitted: () => { committedCalls += 1 }
    }),
    (error) => error.code === 'board_version_conflict'
  )

  assert.equal(updateCalls, 0)
  assert.equal(committedCalls, 0)
  assert.equal(board.currentXml, '<mxfile>current</mxfile>')
})


test('rejects an existing unversioned board instead of sending stale XML', async () => {
  await assert.rejects(
    prepareBoardForSend({
      board: { currentXml: '<mxfile>old</mxfile>', revision: 0 },
      exportXml: async () => '<mxfile>latest</mxfile>',
      updateXml: () => {},
      commitManual: async () => ({})
    }),
    (error) => error.code === 'board_manual_commit_failed'
  )
})
