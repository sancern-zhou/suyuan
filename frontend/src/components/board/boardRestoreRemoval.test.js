import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const srcRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const readSource = path => readFileSync(resolve(srcRoot, path), 'utf8')

test('board version history previews versions without exposing a restore call chain', () => {
  const sources = [
    'api/board.js',
    'stores/reactStore.js',
    'components/board/DrawioBoardPanel.vue',
    'components/reactAnalysis/RightPanelContainer.vue',
    'components/reactAnalysis/MainLayout.vue',
    'views/ReactAnalysisView.vue',
    'views/ReactAnalysisViewRefactored.vue'
  ].map(readSource).join('\n')
  const boardPanelSource = readSource('components/board/DrawioBoardPanel.vue')

  assert.doesNotMatch(sources, /restoreBoardVersion|restoreDrawioBoardVersion/)
  assert.doesNotMatch(sources, /board-version-restore|version-restore/)
  assert.match(boardPanelSource, /<button\s+v-for="version in acceptedVersions"[\s\S]*?@click="previewVersion\(version\)"/)
  assert.match(boardPanelSource, /const previewVersionId = ref\(''\)/)
  assert.match(boardPanelSource, /const previewVersion = async \(version = \{\}\)/)
})

test('selected historical version stays interactive but isolated from editor autosave', () => {
  const boardPanelSource = readSource('components/board/DrawioBoardPanel.vue')

  assert.match(boardPanelSource, /:class="\{ current: getVersionKey\(version\) === displayedVersionId \}"/)
  assert.doesNotMatch(boardPanelSource, /v-if="effectiveReadOnly"/)
  assert.match(boardPanelSource, /v-if="readOnly"/)
  assert.match(boardPanelSource, /const previewSelection = ref\(\[\]\)/)
  assert.match(boardPanelSource, /if \(previewVersionId\.value\)[\s\S]*?previewSelection\.value = selection[\s\S]*?return/)
  assert.match(boardPanelSource, /watch\(\(\) => props\.currentVersionId/)
})

test('sending promotes the currently displayed historical XML instead of the former latest XML', () => {
  const boardPanelSource = readSource('components/board/DrawioBoardPanel.vue')

  assert.doesNotMatch(boardPanelSource, /if \(previewVersionId\.value\) return props\.xml \|\| ''/)
  assert.match(boardPanelSource, /const exportPreviewVersionId = previewVersionId\.value/)
  assert.match(boardPanelSource, /const xml = await boardBridge\.exportCurrentXml\(\)/)
  const exportStart = boardPanelSource.indexOf('const exportCurrentXml = async () =>')
  const exportEnd = boardPanelSource.indexOf('\nconst confirmWorkingVersionCommit', exportStart)
  const exportSource = boardPanelSource.slice(exportStart, exportEnd)
  assert.doesNotMatch(exportSource, /previewVersionId\.value = ''/)
  assert.doesNotMatch(exportSource, /emit\('selection-change', previewSelection\.value\)/)
  assert.match(boardPanelSource, /const confirmWorkingVersionCommit = \(\{ xml \} = \{\}\) =>[\s\S]*?emit\('selection-change', previewSelection\.value\)/)
  assert.match(
    boardPanelSource,
    /registerActiveDrawioBoardExporter\([\s\S]*?exportCurrentXml,[\s\S]*?confirmWorkingVersionCommit,[\s\S]*?previewVersionId\.value \|\| props\.currentVersionId/
  )
})

test('historical version selection stays loading until draw.io confirms the load', () => {
  const boardPanelSource = readSource('components/board/DrawioBoardPanel.vue')

  assert.match(boardPanelSource, /createDrawioBoardLoader/)
  assert.match(boardPanelSource, /if \(!xml\) return false[\s\S]*?if \(!iframeReady\.value && required\)[\s\S]*?board_editor_not_ready/)
  assert.match(boardPanelSource, /editorLoadPromise = loadRequest/)
  assert.match(boardPanelSource, /if \(editorLoadPromise\) await editorLoadPromise/)
  assert.match(boardPanelSource, /if \(previewLoading\.value && !editorLoadPromise\)[\s\S]*?board_editor_not_ready/)
})

test('switching versions recreates draw.io instead of sending a second load to the same iframe', () => {
  const boardPanelSource = readSource('components/board/DrawioBoardPanel.vue')

  assert.match(boardPanelSource, /<iframe[\s\S]*?:key="editorInstanceKey"/)
  assert.match(boardPanelSource, /const restartEditor = \(xml, required = false\) =>/)
  assert.match(boardPanelSource, /editorInstanceKey\.value \+= 1/)
  assert.match(boardPanelSource, /const previewVersion = async[\s\S]*?await restartEditor\(xml, true\)/)
  assert.match(boardPanelSource, /const showCurrentVersion = async[\s\S]*?await restartEditor\(props\.xml, true\)/)
})

test('board version preview validates inline XML before loading it', () => {
  const boardApiSource = readSource('api/board.js')

  assert.doesNotMatch(boardApiSource, /if \(inlineXml\) return inlineXml/)
  assert.match(boardApiSource, /const trimmed = String\(xml \|\| ''\)\.trim\(\)/)
  assert.match(boardApiSource, /throw new Error\('board_version_xml_invalid'\)/)
})

test('starting a preview cancels an in-flight send synchronization', () => {
  const boardPanelSource = readSource('components/board/DrawioBoardPanel.vue')

  assert.match(
    boardPanelSource,
    /const previewVersion = async \(version = \{\}\)[\s\S]*?boardBridge\.cancel\('board_version_preview_started'\)[\s\S]*?await loadBoardVersionXml/
  )
})

test('switching boards clears local preview state and cancels stale synchronization', () => {
  const boardPanelSource = readSource('components/board/DrawioBoardPanel.vue')

  assert.match(boardPanelSource, /watch\(\(\) => props\.boardId/)
  assert.match(
    boardPanelSource,
    /watch\(\(\) => props\.boardId[\s\S]*?boardBridge\.cancel\('board_context_changed'\)[\s\S]*?showCurrentVersion\(\)/
  )
})

test('store confirms the working version only after the manual commit succeeds', () => {
  const storeSource = readSource('stores/reactStore.js')

  assert.match(storeSource, /confirmActiveDrawioBoardCommit/)
  assert.match(storeSource, /onCommitted: \(payload\) => confirmActiveDrawioBoardCommit\(payload\)/)
})
