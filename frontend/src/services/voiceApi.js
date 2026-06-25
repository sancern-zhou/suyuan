const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function transcribeVoice(audioBlob, options = {}) {
  const {
    filename = 'voice.webm',
    language = 'zh'
  } = options

  const formData = new FormData()
  formData.append('file', audioBlob, filename)
  formData.append('language', language)

  const response = await fetch(`${API_BASE_URL}/voice/transcribe`, {
    method: 'POST',
    body: formData
  })
  if (!response.ok) {
    const message = await readErrorMessage(response)
    throw new Error(message || `语音识别失败: HTTP ${response.status}`)
  }
  return await response.json()
}

export function buildSpeechSynthesisBody(text, options = {}) {
  return {
    text,
    voice: options.voice || '冰糖',
    format: options.format || 'wav',
    ...(options.stylePrompt ? { style_prompt: options.stylePrompt } : {})
  }
}

export async function synthesizeVoice(text, options = {}) {
  const response = await fetch(`${API_BASE_URL}/voice/synthesize`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(buildSpeechSynthesisBody(text, options))
  })
  if (!response.ok) {
    const message = await readErrorMessage(response)
    throw new Error(message || `语音合成失败: HTTP ${response.status}`)
  }
  return await response.blob()
}

async function readErrorMessage(response) {
  try {
    const data = await response.json()
    return data?.detail || data?.message || ''
  } catch {
    return ''
  }
}
