/**
 * 报告生成API服务
 */
const API_BASE = '/api/report'

/**
 * 从模板生成报告（传统流水线）
 * @param {Object} params - 生成参数
 * @param {string} params.template_content - 模板内容
 * @param {Object} params.target_time_range - 目标时间范围
 * @param {Object} params.options - 生成选项
 * @returns {Promise<string>} 生成的报告内容
 */
export async function generateFromTemplate(params) {
  const response = await fetch(`${API_BASE}/generate-from-template`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(params)
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  // 处理SSE流
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let reportContent = ''
  let buffer = '' // 累积缓冲区

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk

      const events = parseSSEStream(buffer)

      for (const event of events) {
        if (event.type === 'report_completed') {
          reportContent = event.data.report_content
          return reportContent
        }
      }

      // 清空已处理的完整事件，保留未完成的部分
      buffer = extractRemaining(buffer)
    }
  } finally {
    reader.releaseLock()
  }

  throw new Error('Failed to generate report')
}

/**
 * 从模板生成报告（Agent化，方案B）
 * @param {Object} params - 生成参数
 * @param {string} params.template_content - 模板内容
 * @param {Object} params.target_time_range - 目标时间范围
 * @param {Object} params.options - 生成选项
 * @returns {Promise<string>} 生成的报告内容
 */
export async function generateFromTemplateAgent(params) {
  const response = await fetch(`${API_BASE}/generate-from-template-agent`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(params)
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let reportContent = ''
  let buffer = '' // 累积缓冲区

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk

      const events = parseSSEStream(buffer)

      for (const event of events) {
        if (event.type === 'complete') {
          reportContent = event.data.report_content
          return reportContent
        }
        if (event.type === 'fatal_error' || event.type === 'error') {
          throw new Error(event.data?.error || 'Agent generation failed')
        }
      }

      // 清空已处理的完整事件，保留未完成的部分
      buffer = extractRemaining(buffer)
    }
  } finally {
    reader.releaseLock()
  }

  throw new Error('Failed to generate report (agent)')
}

/**
 * 基于上传的模板文件生成报告（Agent化，方案B，文件上传版）
 * @param {File} file - 模板文件（.docx / .md / .txt）
 * @param {Object} params - 生成参数
 * @param {string} params.start - 开始日期（YYYY-MM-DD）
 * @param {string} params.end - 结束日期（YYYY-MM-DD）
 * @param {string} [params.display] - 展示用时间范围字符串
 * @returns {Promise<{ reportContent: string, sessionId?: string }>} 生成的报告内容 + 会话ID
 */
export async function generateFromTemplateFile(file, params) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('start', params.start)
  formData.append('end', params.end)
  if (params.display) {
    formData.append('display', params.display)
  }

  const response = await fetch(`${API_BASE}/generate-from-template-file`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let reportContent = ''
  let sessionId = undefined
  let buffer = '' // 累积缓冲区

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk

      const events = parseSSEStream(buffer)

      for (const event of events) {
        if (event.type === 'complete') {
          reportContent = event.data.report_content
          sessionId = event.data.session_id
          return { reportContent, sessionId }
        }
        if (event.type === 'fatal_error' || event.type === 'error') {
          throw new Error(event.data?.error || 'Agent generation failed (file)')
        }
      }

      // 清空已处理的完整事件，保留未完成的部分
      buffer = extractRemaining(buffer)
    }
  } finally {
    reader.releaseLock()
  }

  throw new Error('Failed to generate report (agent, file)')
}

/**
 * 从保存的模板生成报告
 * @param {string} templateId - 模板ID
 * @param {Object} params - 生成参数
 * @returns {Promise<string>} 生成的报告内容
 */
export async function generateFromSavedTemplate(templateId, params) {
  const response = await fetch(`${API_BASE}/templates/${templateId}/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(params)
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  // 处理SSE流
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let reportContent = ''
  let buffer = '' // 累积缓冲区

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk

      const events = parseSSEStream(buffer)

      for (const event of events) {
        if (event.type === 'report_completed') {
          reportContent = event.data.report_content
          return reportContent
        }
      }

      // 清空已处理的完整事件，保留未完成的部分
      buffer = extractRemaining(buffer)
    }
  } finally {
    reader.releaseLock()
  }

  throw new Error('Failed to generate report')
}

/**
 * 获取模板列表
 * @returns {Promise<Array>} 模板列表
 */
export async function listTemplates() {
  const response = await fetch(`${API_BASE}/templates`)

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  return await response.json()
}

/**
 * 创建模板
 * @param {Object} params - 模板参数
 * @returns {Promise<Object>} 创建的模板
 */
export async function createTemplate(params) {
  const formData = new FormData()
  formData.append('name', params.name)
  formData.append('source_report', params.source_report)
  if (params.description) {
    formData.append('description', params.description)
  }

  const response = await fetch(`${API_BASE}/templates`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  return await response.json()
}

/**
 * 上传模板文件
 * @param {File} file - 模板文件
 * @param {Object} metadata - 元数据
 * @returns {Promise<Object>} 上传结果
 */
export async function uploadTemplate(file, metadata = {}) {
  const formData = new FormData()
  formData.append('file', file)

  if (metadata.name) {
    formData.append('name', metadata.name)
  }
  if (metadata.description) {
    formData.append('description', metadata.description)
  }

  const response = await fetch(`${API_BASE}/upload-template`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  return await response.json()
}

/**
 * 解析SSE流（支持跨chunk事件）
 * @param {string} buffer - 累积的数据缓冲区
 * @returns {Array} 完整事件列表
 */
function parseSSEStream(buffer) {
  const events = []
  const lines = buffer.split('\n')

  let currentEvent = null
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (line.startsWith('event:')) {
      if (currentEvent && currentEvent.data) {
        // 只有当data字段完整时才推入事件
        events.push(currentEvent)
      }
      currentEvent = {
        type: line.substring(6).trim(),
        data: null
      }
    } else if (line.startsWith('data:')) {
      if (currentEvent) {
        const dataStr = line.substring(5).trim()
        try {
          currentEvent.data = JSON.parse(dataStr)
        } catch (e) {
          // JSON解析失败，说明数据不完整，停止处理
          break
        }
      }
    } else if (line === '' && currentEvent && currentEvent.data) {
      // 空行表示事件结束
      events.push(currentEvent)
      currentEvent = null
    }

    i++
  }

  return events
}

/**
 * 提取缓冲区中未处理的部分
 * @param {string} buffer - 累积的数据缓冲区
 * @returns {string} 剩余未处理的数据
 */
function extractRemaining(buffer) {
  // 找到最后一个完整事件的位置
  const lines = buffer.split('\n')
  let lastCompleteIndex = -1

  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i] === '') {
      // 找到空行，表示前面是完整事件
      lastCompleteIndex = i
      break
    }
  }

  if (lastCompleteIndex === -1) {
    // 没有完整事件，保留整个缓冲区
    return buffer
  }

  // 返回最后一个完整事件之后的内容
  return lines.slice(lastCompleteIndex + 1).join('\n')
}

export default {
  generateFromTemplate,
  generateFromTemplateAgent,
  generateFromTemplateFile,
  generateFromSavedTemplate,
  listTemplates,
  createTemplate,
  uploadTemplate
}
