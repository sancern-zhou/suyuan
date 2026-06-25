import { synthesizeVoice } from './voiceApi.js'

const SENTENCE_ENDINGS = new Set(['。', '！', '？', '!', '?', '\n'])

export function splitCompleteSentences(text = '') {
  const sentences = []
  let start = 0
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (!SENTENCE_ENDINGS.has(char)) continue

    const sentence = text.slice(start, index + 1)
    if (sentence.trim()) {
      sentences.push(sentence)
    }
    start = index + 1
  }

  return {
    sentences,
    rest: text.slice(start)
  }
}

export function createQueryVoicePlaybackQueue(options = {}) {
  const synthesize = options.synthesize || synthesizeVoice
  const createAudio = options.createAudio || ((url) => new Audio(url))
  const voice = options.voice || '冰糖'
  const stylePrompt = options.stylePrompt || '用专业、清晰、平稳的语气播报空气质量分析结果。'

  let buffer = ''
  let closed = false
  let stopped = false
  let playing = false
  let currentAudio = null
  let resolveCurrentPlayback = null
  const queue = []
  let drainPromise = Promise.resolve()

  const enqueue = (text) => {
    const normalized = String(text || '').trim()
    if (!normalized || stopped) return
    queue.push({
      text: normalized,
      audioPromise: synthesize(normalized, { voice, stylePrompt })
    })
    drainPromise = drainPromise.then(playQueued)
  }

  const playQueued = async () => {
    if (playing || stopped) return
    playing = true
    try {
      while (queue.length > 0 && !stopped) {
        const item = queue.shift()
        await playOne(item)
      }
    } finally {
      playing = false
    }
  }

  const playOne = async (item) => {
    if (typeof URL === 'undefined') return
    const audioBlob = await item.audioPromise
    const audioUrl = URL.createObjectURL(audioBlob)
    try {
      const audio = createAudio(audioUrl)
      currentAudio = audio
      await new Promise((resolve) => {
        const finishPlayback = () => {
          if (resolveCurrentPlayback === finishPlayback) {
            resolveCurrentPlayback = null
          }
          resolve()
        }
        resolveCurrentPlayback = finishPlayback
        audio.onended = finishPlayback
        audio.onerror = finishPlayback
        const result = audio.play()
        if (result && typeof result.then === 'function') {
          result.catch(finishPlayback)
        }
      })
    } finally {
      if (currentAudio?.src === audioUrl || currentAudio) {
        currentAudio = null
      }
      resolveCurrentPlayback = null
      URL.revokeObjectURL(audioUrl)
    }
  }

  return {
    pushChunk(chunk) {
      if (stopped || closed) return
      buffer += String(chunk || '')
      const { sentences, rest } = splitCompleteSentences(buffer)
      buffer = rest
      sentences.forEach(enqueue)
    },

    finish() {
      if (stopped) return
      const remaining = buffer.trim()
      buffer = ''
      enqueue(remaining)
      closed = true
    },

    stop() {
      closed = true
      stopped = true
      buffer = ''
      queue.length = 0
      if (currentAudio) {
        if (typeof currentAudio.pause === 'function') {
          currentAudio.pause()
        }
        try {
          currentAudio.currentTime = 0
        } catch {
          // Some browser audio implementations can reject seeking before metadata loads.
        }
      }
      resolveCurrentPlayback?.()
    },

    drain() {
      return drainPromise
    }
  }
}
