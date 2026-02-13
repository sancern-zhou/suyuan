// ReAct Agent API客户端
// 处理与ReAct Agent的SSE流式通信

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

class ReactAgentAPI {
  constructor() {
    this.controller = null
  }

  // 清理JSON数据中的无效值
  sanitizeJSONString(jsonStr) {
    // 将NaN, Infinity, -Infinity替换为null，确保JSON可解析
    return jsonStr
      .replace(/\bNaN\b/g, 'null')
      .replace(/\bInfinity\b/g, 'null')
      .replace(/\b-Infinity\b/g, 'null')
  }

  // 流式分析
  async analyze(query, options = {}) {
    const {
      sessionId = null,
      enhanceWithHistory = true,
      maxIterations = 10,
      debugMode = false,
      assistantMode = null,  // 助手模式
      precision = 'standard',  // 精度模式选项 (fast/standard/full)
      enableMultiExpert = false,  // ✅ 是否启用多专家系统
      onEvent
    } = options

    // 取消之前的请求
    if (this.controller) {
      this.controller.abort()
    }
    this.controller = new AbortController()

    const url = `${API_BASE_URL}/agent/analyze`
    const body = {
      query,
      session_id: sessionId,
      enhance_with_history: enhanceWithHistory,
      max_iterations: maxIterations,
      debug_mode: debugMode,
      assistant_mode: assistantMode,  // 传递助手模式
      precision: precision,  // 精度模式选项 (fast/standard/full)
      enable_multi_expert: enableMultiExpert  // ✅ 传递多专家开关
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
        signal: this.controller.signal
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
      this.controller = null
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Request was aborted')
      } else {
        console.error('Analysis failed:', error)
        throw error
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
      console.error('Get tools failed:', error)
      throw error
    }
  }

  // 健康检查
  async healthCheck() {
    const url = `${API_BASE_URL}/agent/health`

    try {
      const response = await fetch(url)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return await response.json()
    } catch (error) {
      console.error('Health check failed:', error)
      throw error
    }
  }

  // 取消当前请求
  cancel() {
    if (this.controller) {
      this.controller.abort()
      this.controller = null
    }
  }
}

// 创建实例
export const reactAgentApi = new ReactAgentAPI()

// 导出便捷方法
export const agentAPI = {
  analyze: (query, options) => reactAgentApi.analyze(query, options),
  simpleQuery: (query, maxIterations) => reactAgentApi.simpleQuery(query, maxIterations),
  getTools: () => reactAgentApi.getTools(),
  healthCheck: () => reactAgentApi.healthCheck(),
  cancel: () => reactAgentApi.cancel()
}
