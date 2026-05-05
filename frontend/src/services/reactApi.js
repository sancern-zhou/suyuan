// ReAct Agent API客户端
// 处理与ReAct Agent的SSE流式通信

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

class ReactAgentAPI {
  constructor() {
    this.controller = null
    this.controllers = new Map()
  }

  // 清理JSON数据中的无效值
  sanitizeJSONString(jsonStr) {
    // 将NaN, Infinity, -Infinity替换为null，确保JSON可解析
    return jsonStr
      .replace(/\bNaN\b/g, 'null')
      .replace(/\bInfinity\b/g, 'null')
      .replace(/\b-Infinity\b/g, 'null')
  }

  // 流式分析（新架构）
  async analyze(query, options = {}) {
    const {
      sessionId = null,
      enhanceWithHistory = true,
      maxIterations = 30,
      debugMode = false,
      assistantMode = null,  // 助手模式
      agentMode = 'expert',  // ✅ 双模式架构：assistant | expert
      knowledgeBaseIds = null,  // ✅ 知识库ID列表
      attachments = null,  // ✅ 附件列表
      userIdentifier = null,  // ✅ 用户标识（跨会话持久化）
      requestKey = sessionId,
      onEvent
    } = options

    const url = `${API_BASE_URL}/agent/analyze`
    const body = {
      query,
      session_id: sessionId,
      user_id: userIdentifier,  // ✅ 传递用户标识
      enhance_with_history: enhanceWithHistory,
      max_iterations: maxIterations,
      debug_mode: debugMode,
      assistant_mode: assistantMode,  // 传递助手模式
      mode: agentMode,  // ✅ 双模式架构
      knowledge_base_ids: knowledgeBaseIds,  // ✅ 传递知识库ID列表
      attachments: attachments  // ✅ 传递附件列表
    }

    return this._streamRequest(url, body, onEvent, requestKey || sessionId || `request_${Date.now()}`)
  }

  // ✅ 新增：ExpertRouterV3 多专家并行快速溯源（旧架构）
  async analyzeV3(query, options = {}) {
    const {
      sessionId = null,
      precision = 'standard',  // fast/standard/full
      enableCheckpoint = false,
      requestKey = sessionId,
      onEvent
    } = options

    const url = `${API_BASE_URL}/agent/analyze-v3`
    const body = {
      query,
      session_id: sessionId,
      precision: precision,
      enable_checkpoint: enableCheckpoint
    }

    return this._streamRequest(url, body, onEvent, requestKey || sessionId || `request_${Date.now()}`)
  }

  // ✅ 新增：内部方法 - 统一的SSE流处理
  async _streamRequest(url, body, onEvent, requestKey = 'default') {
    if (this.controllers.has(requestKey)) {
      this.controllers.get(requestKey).abort()
      this.controllers.delete(requestKey)
    }

    const controller = new AbortController()
    this.controllers.set(requestKey, controller)
    this.controller = controller

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
        signal: controller.signal
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      if (!response.body) {
        throw new Error('Response body is null')
      }

      // 处理SSE流
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const processStream = async () => {
        while (true) {
          const { done, value } = await reader.read()

          if (done) {
            break
          }

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() // 保存不完整的行

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6).trim()
              if (data) {
                try {
                  // 清理JSON字符串中的无效值
                  const sanitizedData = this.sanitizeJSONString(data)
                  const event = JSON.parse(sanitizedData)
                  if (onEvent && typeof onEvent === 'function') {
                    onEvent(event)
                  }
                } catch (e) {
                  console.error('Failed to parse SSE data:', data, e)
                }
              }
            }
          }
        }
      }

      await processStream()
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Request was aborted')
      } else {
        console.error('Analysis failed:', error)
        throw error
      }
    } finally {
      if (this.controllers.get(requestKey) === controller) {
        this.controllers.delete(requestKey)
      }
      if (this.controller === controller) {
        this.controller = null
      }
    }
  }

  // 简单查询（非流式）
  async simpleQuery(query, maxIterations = 10) {
    const url = `${API_BASE_URL}/agent/query`
    const body = {
      query,
      max_iterations: maxIterations
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body)
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      return await response.json()
    } catch (error) {
      console.error('Query failed:', error)
      throw error
    }
  }

  // 获取工具列表
  async getTools() {
    const url = `${API_BASE_URL}/agent/tools`

    try {
      const response = await fetch(url)

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      return await response.json()
    } catch (error) {
      console.error('Failed to get tools:', error)
      throw error
    }
  }

  // 取消请求
  cancel(requestKey = null) {
    if (requestKey) {
      const controller = this.controllers.get(requestKey)
      if (controller) {
        controller.abort()
        this.controllers.delete(requestKey)
      }
      if (this.controller === controller) {
        this.controller = null
      }
      return
    }

    for (const controller of this.controllers.values()) {
      controller.abort()
    }
    this.controllers.clear()
    this.controller = null
  }
}

// 导出单例
export const agentAPI = new ReactAgentAPI()
