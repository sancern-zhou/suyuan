export class BoardSyncError extends Error {
  constructor(code, message = code) {
    super(message)
    this.name = 'BoardSyncError'
    this.code = code
  }
}

const parseMessage = (data) => {
  if (data && typeof data === 'object') return data
  if (typeof data !== 'string') return null
  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}

const extractXml = (message = {}) => {
  const value = message.xml || message.data || ''
  if (typeof value !== 'string') return ''
  const trimmed = value.trim()
  return trimmed.startsWith('<mxfile') || trimmed.startsWith('<mxGraphModel') ? value : ''
}

export const createDrawioBoardBridge = ({
  getTargetWindow,
  allowedOrigin,
  postMessage,
  timeoutMs = 5000,
  setTimer = setTimeout,
  clearTimer = clearTimeout
}) => {
  let pending = null

  const settle = (kind, value) => {
    if (!pending) return
    const current = pending
    pending = null
    clearTimer(current.timeoutId)
    current[kind](value)
  }

  const exportCurrentXml = () => {
    const target = getTargetWindow?.()
    if (!target) {
      return Promise.reject(new BoardSyncError('board_editor_not_ready', '画板编辑器尚未就绪'))
    }
    if (pending) {
      return Promise.reject(new BoardSyncError('board_sync_in_progress', '画板正在同步'))
    }

    return new Promise((resolve, reject) => {
      const timeoutId = setTimer(() => {
        settle('reject', new BoardSyncError('board_sync_timeout', '同步画板超时，请重试'))
      }, timeoutMs)
      pending = { resolve, reject, timeoutId }
      const payload = JSON.stringify({ action: 'export', format: 'xml' })
      if (postMessage) {
        postMessage(payload, allowedOrigin)
      } else {
        target.postMessage(payload, allowedOrigin)
      }
    })
  }

  const handleMessage = (event) => {
    const target = getTargetWindow?.()
    if (!target || event?.source !== target || event?.origin !== allowedOrigin) return false
    if (!pending) return false
    const message = parseMessage(event.data)
    if (!message || message.event !== 'export') return false
    const isXmlResponse = typeof message.xml === 'string' || message.format === 'xml'
    if (!isXmlResponse) return false
    const xml = extractXml(message)
    if (!xml) {
      settle('reject', new BoardSyncError('board_sync_invalid_xml', '画板返回的 XML 无效'))
      return true
    }
    settle('resolve', xml)
    return true
  }

  const cancel = (code = 'board_sync_cancelled') => {
    settle('reject', new BoardSyncError(code))
  }

  return { exportCurrentXml, handleMessage, cancel }
}

let activeBoardExporter = null

export const registerActiveDrawioBoardExporter = (exporter) => {
  activeBoardExporter = typeof exporter === 'function' ? exporter : null
  return () => {
    if (activeBoardExporter === exporter) activeBoardExporter = null
  }
}

export const exportActiveDrawioBoardXml = async () => {
  if (!activeBoardExporter) {
    throw new BoardSyncError('board_editor_not_ready', '画板编辑器尚未就绪')
  }
  return await activeBoardExporter()
}
