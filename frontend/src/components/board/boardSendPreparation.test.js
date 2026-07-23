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
    exportXml: async () => {
      calls.push('sync')
      return '<mxfile>latest</mxfile>'
    },
    updateXml: (xml) => {
      calls.push(`update:${xml}`)
      board.currentXml = xml
    },
    commitManual: async (payload) => {
      calls.push(`commit:${payload.base_revision}:${payload.xml}`)
      return {
        board_id: 'board-1',
        current_version_id: 'version-2',
        revision: 2,
        version: { version_id: 'version-2', xml_sha256: 'hash-2' }
      }
    }
  })

  assert.deepEqual(calls, [
    'sync',
    'update:<mxfile>latest</mxfile>',
    'commit:1:<mxfile>latest</mxfile>'
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
