import { BoardSyncError } from './drawioBoardBridge.js'


export const prepareBoardForSend = async ({ board, exportXml, updateXml, commitManual }) => {
  if (!board?.currentXml) return { context: null, response: null }
  if (!board.activeBoardId) {
    throw new BoardSyncError('board_manual_commit_failed', '当前画板尚未建立服务端版本，请重新加载会话')
  }

  const xml = await exportXml()
  updateXml(xml)
  const response = await commitManual({
    base_revision: Number(board.revision || 0),
    xml
  })
  const version = response?.version || {}
  if (!response?.current_version_id || !Number.isFinite(Number(response?.revision))) {
    throw new BoardSyncError('board_manual_commit_failed', '画板版本提交失败')
  }

  board.activeBoardId = response.board_id || board.activeBoardId
  board.currentVersionId = response.current_version_id
  board.baseVersionId = response.current_version_id
  board.currentVersionSha256 = version.xml_sha256 || board.currentVersionSha256 || null
  board.revision = Number(response.revision)
  board.version = Number(version.version_number || board.version || 0)
  board.dirty = false

  return {
    response,
    context: {
      board_id: board.activeBoardId,
      version_id: board.currentVersionId,
      revision: board.revision,
      selected_cells: Array.isArray(board.selectedCells) ? board.selectedCells : []
    }
  }
}
