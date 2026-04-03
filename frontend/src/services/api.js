// API客户端 - 处理与后端的所有通信

// API基础配置
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

class ApiClient {
  constructor() {
    this.baseURL = API_BASE_URL
    this.controller = null // 用于取消请求
  }

  // 通用请求方法
  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`
    const method = (options.method || 'GET').toUpperCase()
    const headers = { ...(options.headers || {}) }
    if (method !== 'GET' && method !== 'HEAD' && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json'
    }
    const config = {
      ...options,
      method,
      headers,
    }

    try {
      const response = await fetch(url, config)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return await response.json()
    } catch (error) {
      console.error('API request failed:', error)
      throw error
    }
  }

  // POST 请求方法
  async post(endpoint, data = {}) {
    const url = `${this.baseURL}${endpoint}`
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      })
      if (!response.ok) {
        const errorText = await response.text()
        let errorDetail = errorText
        try {
          const errorJson = JSON.parse(errorText)
          errorDetail = errorJson.detail || errorJson.message || errorText
        } catch (e) {
          // Use raw text
        }
        const error = new Error(errorDetail)
        error.response = { data: errorJson }
        throw error
      }
      return await response.json()
    } catch (error) {
      console.error('API POST request failed:', error)
      throw error
    }
  }

  // 健康检查
  async healthCheck() {
    return this.request('/health')
  }

  // 获取配置
  async getConfig() {
    return this.request('/config')
  }

  // =============== Fetchers 管理 ===============

  // 获取系统状态（包括Fetchers）
  async getSystemStatus() {
    return this.request('/system/status')
  }

  // 获取Fetchers调度器状态
  async getFetchersStatus() {
    return this.request('/system/status')
  }

  // 手动触发Fetcher
  async triggerFetcher(fetcherName) {
    return this.request(`/fetchers/trigger/${fetcherName}`, {
      method: 'POST'
    })
  }

  // 启动所有Fetchers
  async startAllFetchers() {
    return this.request('/fetchers/start', {
      method: 'POST'
    })
  }

  // 停止所有Fetchers
  async stopAllFetchers() {
    return this.request('/fetchers/stop', {
      method: 'POST'
    })
  }

  // 暂停指定Fetcher
  async pauseFetcher(fetcherName) {
    return this.request(`/fetchers/pause/${fetcherName}`, {
      method: 'POST'
    })
  }

  // 恢复指定Fetcher
  async resumeFetcher(fetcherName) {
    return this.request(`/fetchers/resume/${fetcherName}`, {
      method: 'POST'
    })
  }

  // 流式对话分析
  async streamAnalysis(message, sessionId = null, onEvent) {
    // 取消之前的请求
    if (this.controller) {
      this.controller.abort()
    }
    this.controller = new AbortController()

    const url = `${this.baseURL}/chat`
    const body = {
      message,
      session_id: sessionId,
      stream: true
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

      // 处理流式响应
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
                  const event = JSON.parse(data)
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
        console.error('Stream analysis failed:', error)
        throw error
      }
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

// 创建API客户端实例
export const apiClient = new ApiClient()

// 导出便捷方法
export const api = {
  healthCheck: () => apiClient.healthCheck(),
  getConfig: () => apiClient.getConfig(),
  streamAnalysis: (message, sessionId, onEvent) =>
    apiClient.streamAnalysis(message, sessionId, onEvent),
  cancel: () => apiClient.cancel(),
  post: (endpoint, data) => apiClient.post(endpoint, data),

  // Fetchers 管理
  getSystemStatus: () => apiClient.getSystemStatus(),
  getFetchersStatus: () => apiClient.getFetchersStatus(),
  triggerFetcher: (fetcherName) => apiClient.triggerFetcher(fetcherName),
  startAllFetchers: () => apiClient.startAllFetchers(),
  stopAllFetchers: () => apiClient.stopAllFetchers(),
  pauseFetcher: (fetcherName) => apiClient.pauseFetcher(fetcherName),
  resumeFetcher: (fetcherName) => apiClient.resumeFetcher(fetcherName)
}
