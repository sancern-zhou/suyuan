import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createSelectionRestoreGuard,
  reconcileSelectionDraft
} from './inputBoxSelectionDraft.js'

test('restores only skills and files still valid in the target session and mode', () => {
  const result = reconcileSelectionDraft(
    { skillId: 'trend', fileIds: ['f1', 'missing'], policyFileIds: ['f1'] },
    [{ id: 'trend', compatible: true }],
    [{ id: 'f1', name: '数据.xlsx' }]
  )
  assert.equal(result.skill.id, 'trend')
  assert.deepEqual(result.files.map(file => file.id), ['f1'])
  assert.equal(result.files[0].pinnedPolicy, true)
})

test('drops a skill that is unavailable or incompatible in the new mode', () => {
  assert.equal(reconcileSelectionDraft(
    { skillId: 'trend', fileIds: [] },
    [{ id: 'trend', compatible: false }],
    []
  ).skill, null)
})

test('invalidates an older restore when upload creates the first session', () => {
  const guard = createSelectionRestoreGuard()
  const staleRestore = guard.begin(null, 'board')

  guard.invalidate()

  assert.equal(guard.isCurrent(staleRestore, 'board_session_1', 'board'), false)
})

test('applies a restore only to the same session and mode', () => {
  const guard = createSelectionRestoreGuard()
  const restore = guard.begin('board_session_1', 'board')

  assert.equal(guard.isCurrent(restore, 'board_session_1', 'board'), true)
  assert.equal(guard.isCurrent(restore, 'board_session_2', 'board'), false)
  assert.equal(guard.isCurrent(restore, 'board_session_1', 'chart'), false)
})
