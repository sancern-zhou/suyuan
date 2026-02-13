/**
 * 知识问答API模块
 *
 * 基于知识库的RAG问答系统
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const BASE_URL = `${API_BASE_URL}/knowledge-qa`

/**
 * 流式知识问答
 * @param {string} query - 用户问题
 * @param {Object} options - 选项
 * @param {string} options.session_id - 会话ID
 * @param {string[]} options.knowledge_base_ids - 知识库ID列表
 * @param {number} options.top_k - 返回结果数量
 * @param {number} options.score_threshold - 相似度阈值
 * @param {boolean} options.use_reranker - 是否使用Reranker
 * @param {Function} onMessage - 消息回调
 * @param {Function} onError - 错误回调
 * @param {Function} onComplete - 完成回调
 * @returns {Promise<string>} session_id
 */
export async function knowledgeQAStream(query, options = {}, onMessage, onError, onComplete) {
  const {
    session_id = null,
    knowledge_base_ids = null,
    top_k = 5,
    score_threshold = null,
    use_reranker = true
  } = options

  const requestBody = {
    query,
    session_id,
    knowledge_base_ids,
    top_k,
    score_threshold,
    use_reranker
  }

  const userId = localStorage.getItem('userId') || 'anonymous'
  const headers = {
    'Content-Type': 'application/json',
    'X-User-Id': userId
  }

  return new Promise((resolve, reject) => {
    // 使用 fetch + ReadableStream 实现 POST 请求的 SSE
    fetch(`${BASE_URL}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId
      },
      body: JSON.stringify(requestBody)
    })
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let finalSessionId = session_id

        function processChunk() {
          reader.read().then(({ done, value }) => {
            if (done) {
              if (onComplete) {
                onComplete()
              }
              resolve(finalSessionId)
              return
            }

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const eventData = JSON.parse(line.slice(6))

                  if (eventData.type === 'start') {
                    finalSessionId = eventData.data.session_id
                  }

                  if (onMessage) {
                    onMessage(eventData)
                  }

                  if (eventData.type === 'complete' && onComplete) {
                    onComplete(eventData.data)
                    resolve(finalSessionId)
                    return
                  }

                  if (eventData.type === 'fatal_error') {
                    const error = new Error(eventData.data?.error || 'Unknown error')
                    if (onError) {
                      onError(error)
                    }
                    reject(error)
                    return
                  }
                } catch (e) {
                  console.warn('Failed to parse SSE event:', line.slice(0, 100))
                }
              }
            }

            processChunk()
          })
        }

        processChunk()
      })
      .catch(error => {
        console.error('Knowledge QA stream failed:', error)
        if (onError) {
          onError(error)
        }
        reject(error)
      })
  })
}

/**
 * 非流式知识问答
 * @param {string} query - 用户问题
 * @param {Object} options - 选项
 * @returns {Promise<Object>} 问答结果
 */
export async function knowledgeQA(query, options = {}) {
  const {
    session_id = null,
    knowledge_base_ids = null,
    top_k = 5,
    score_threshold = null,
    use_reranker = true
  } = options

  const requestBody = {
    query,
    session_id,
    knowledge_base_ids,
    top_k,
    score_threshold,
    use_reranker
  }

  const userId = localStorage.getItem('userId') || 'anonymous'

  const response = await fetch(BASE_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId
    },
    body: JSON.stringify(requestBody)
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || `HTTP error! status: ${response.status}`)
  }

  return await response.json()
}

/**
 * 知识问答健康检查
 */
export async function knowledgeQAHealth() {
  const response = await fetch(`${BASE_URL}/health`)

  if (!response.ok) {
    throw new Error('Knowledge QA service unhealthy')
  }

  return await response.json()
}

/**
 * 获取对话历史
 * @param {string} sessionId - 会话ID
 * @returns {Promise<Object>} 对话历史
 */
export async function getConversationHistory(sessionId) {
  const userId = localStorage.getItem('userId') || 'anonymous'
  const response = await fetch(`${BASE_URL}/history/${sessionId}`, {
    headers: {
      'X-User-Id': userId
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '获取对话历史失败' }))
    throw new Error(error.detail || '获取对话历史失败')
  }

  return await response.json()
}

/**
 * 获取最近的对话轮次
 * @param {string} sessionId - 会话ID
 * @param {number} limit - 返回数量
 * @returns {Promise<Object>} 最近轮次
 */
export async function getRecentTurns(sessionId, limit = 10) {
  const userId = localStorage.getItem('userId') || 'anonymous'
  const response = await fetch(`${BASE_URL}/history/${sessionId}/recent?limit=${limit}`, {
    headers: {
      'X-User-Id': userId
    }
  })

  if (!response.ok) {
    throw new Error('获取对话轮次失败')
  }

  return await response.json()
}

/**
 * 删除会话
 * @param {string} sessionId - 会话ID
 * @returns {Promise<Object>} 删除结果
 */
export async function deleteConversationSession(sessionId) {
  const userId = localStorage.getItem('userId') || 'anonymous'
  const response = await fetch(`${BASE_URL}/history/${sessionId}`, {
    method: 'DELETE',
    headers: {
      'X-User-Id': userId
    }
  })

  if (!response.ok) {
    throw new Error('删除会话失败')
  }

  return await response.json()
}

/**
 * 归档会话
 * @param {string} sessionId - 会话ID
 * @returns {Promise<Object>} 归档结果
 */
export async function archiveConversationSession(sessionId) {
  const userId = localStorage.getItem('userId') || 'anonymous'
  const response = await fetch(`${BASE_URL}/history/${sessionId}/archive`, {
    method: 'POST',
    headers: {
      'X-User-Id': userId
    }
  })

  if (!response.ok) {
    throw new Error('归档会话失败')
  }

  return await response.json()
}

/**
 * 列出用户会话
 * @param {Object} options - 选项
 * @param {string} options.status - 状态过滤
 * @param {number} options.limit - 返回数量
 * @param {number} options.offset - 偏移量
 * @returns {Promise<Object>} 会话列表
 */
export async function listUserSessions(options = {}) {
  const { status, limit = 20, offset = 0 } = options
  const userId = localStorage.getItem('userId') || 'anonymous'

  const params = new URLSearchParams()
  if (status) params.append('status', status)
  params.append('limit', limit)
  params.append('offset', offset)

  const response = await fetch(`${BASE_URL}/history/list?${params}`, {
    headers: {
      'X-User-Id': userId
    }
  })

  if (!response.ok) {
    throw new Error('获取会话列表失败')
  }

  return await response.json()
}
