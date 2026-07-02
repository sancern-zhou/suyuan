export function shouldShowVoiceControls(mode) {
  return mode === 'query'
}

export function getPreferredRecordingMimeType() {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4'
  ]
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return ''
  }
  return candidates.find(type => MediaRecorder.isTypeSupported(type)) || ''
}

export function getVoiceRecordingAvailability(env = {}) {
  const protocol = env.protocol ?? (typeof window !== 'undefined' ? window.location?.protocol : '')
  const hostname = env.hostname ?? (typeof window !== 'undefined' ? window.location?.hostname : '')
  const secureContext = env.isSecureContext ?? (
    typeof window !== 'undefined' ? window.isSecureContext : false
  )
  const hasMediaDevices = env.hasMediaDevices ?? (
    typeof navigator !== 'undefined' && !!navigator.mediaDevices
  )
  const hasGetUserMedia = env.hasGetUserMedia ?? (
    typeof navigator !== 'undefined' && typeof navigator.mediaDevices?.getUserMedia === 'function'
  )
  const hasMediaRecorder = env.hasMediaRecorder ?? (typeof MediaRecorder !== 'undefined')
  const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]'

  if (protocol === 'http:' && !secureContext && !isLocalhost) {
    return {
      available: false,
      reason: 'insecure_context',
      message: '语音录制需要 HTTPS 安全访问；开发环境请使用 localhost，服务器访问请配置 HTTPS。'
    }
  }

  if (!hasMediaDevices || !hasGetUserMedia) {
    return {
      available: false,
      reason: 'missing_get_user_media',
      message: '当前浏览器没有开放麦克风录制能力，请检查是否为 HTTPS、浏览器权限或企业安全策略限制。'
    }
  }

  if (!hasMediaRecorder) {
    return {
      available: false,
      reason: 'missing_media_recorder',
      message: '当前浏览器不支持 MediaRecorder 录音，请升级 Edge/Chrome 或更换浏览器。'
    }
  }

  return {
    available: true,
    reason: 'available',
    message: ''
  }
}

export function createVoiceFilename(mimeType = '') {
  const normalized = mimeType.split(';')[0]
  const extension = normalized.includes('mp4')
    ? 'mp4'
    : normalized.includes('ogg')
      ? 'ogg'
      : normalized.includes('wav')
        ? 'wav'
        : 'webm'
  return `voice-${Date.now()}.${extension}`
}
