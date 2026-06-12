import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const storePath = resolve(__dirname, './reactStore.js')
const apiPath = resolve(__dirname, '../services/reactApi.js')
const storeSource = readFileSync(storePath, 'utf8')
const apiSource = readFileSync(apiPath, 'utf8')

for (const field of [
  'activeBoardId',
  'title',
  'currentXml',
  'previousXml',
  'selectedCells',
  'pendingSnapshotAttachment',
  'version',
  'dirty',
  'updatedAt'
]) {
  assert.match(
    storeSource,
    new RegExp(`${field}:`),
    `createEmptyModeState should initialize board field ${field}`
  )
}

assert.match(
  storeSource,
  /applyDrawioBoardToolResult\(/,
  'reactStore should expose an action for create_drawio_board tool result payloads'
)

assert.match(
  storeSource,
  /restoreDrawioBoardFromSession\(/,
  'reactStore should expose an action to restore draw.io board state from session data'
)

assert.match(
  storeSource,
  /metadata\?\.drawio_board|metadata\.drawio_board/,
  'session restore should read metadata.drawio_board as the authoritative restored board state'
)

assert.match(
  storeSource,
  /pendingSnapshotAttachment\s*=\s*null/,
  'restored board state should not revive unsent pending board snapshot attachments'
)

assert.match(
  storeSource,
  /updateDrawioBoardXml\(/,
  'reactStore should expose an action for user-edited draw.io XML'
)

assert.match(
  storeSource,
  /updateDrawioBoardSelection\(/,
  'reactStore should expose an action for draw.io cell selection'
)

assert.match(
  storeSource,
  /confirmDrawioBoardSnapshot\(/,
  'reactStore should expose an action to upload confirmed board PNG snapshots'
)

assert.match(
  storeSource,
  /consumeDrawioBoardSnapshotAttachment\(/,
  'reactStore should consume pending board snapshots when the next chart request is sent'
)

assert.match(
  storeSource,
  /buildBoardContext\([^)]*\)/,
  'reactStore should expose a helper to build board_context'
)

assert.doesNotMatch(
  storeSource.match(/buildBoardContext\([^]*?^\s*}\s*,/m)?.[0] || '',
  /previous_xml:/,
  'buildBoardContext should not send previous_xml in board_context'
)

assert.match(
  storeSource,
  /actualMode\s*===\s*'chart'\s*\?\s*this\.buildBoardContext\(/,
  'startAnalysis should build boardContext only for chart mode'
)

assert.match(
  storeSource,
  /actualMode\s*===\s*'chart'[\s\S]*consumeDrawioBoardSnapshotAttachment\(/,
  'startAnalysis should only auto-attach confirmed board snapshots in chart mode'
)

assert.match(
  storeSource,
  /source:\s*['"]drawio_board_snapshot['"]/,
  'confirmed board snapshot attachments should be marked with a drawio_board_snapshot source'
)

assert.match(
  storeSource,
  /metadata\?\.generator\s*===\s*'create_drawio_board'|metadata\.generator\s*===\s*'create_drawio_board'/,
  'tool result handling should detect metadata.generator=create_drawio_board'
)

assert.match(
  storeSource,
  /data\?\.artifact_kind\s*===\s*'drawio_board'|data\.artifact_kind\s*===\s*'drawio_board'/,
  'tool result handling should detect data.artifact_kind=drawio_board'
)

assert.match(
  apiSource,
  /boardContext\s*=\s*null/,
  'reactApi.analyze should accept a boardContext option'
)

assert.match(
  apiSource,
  /if\s*\(\s*boardContext\s*!==\s*null\s*\)[\s\S]*body\.board_context\s*=\s*boardContext/,
  'reactApi.analyze should include board_context only when boardContext is non-null'
)

console.log('draw.io board source checks passed')
