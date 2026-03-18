/**
 * 知识库API模块
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const BASE_URL = `${API_BASE_URL}/knowledge-base`

/**
 * 通用请求方法
 */
async function request(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...(options.headers || {}) }

  // 非 FormData 时设置 JSON Content-Type
  if (method !== 'GET' && method !== 'HEAD' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  // 添加用户ID（如果有）
  const userId = localStorage.getItem('userId') || 'anonymous'
  headers['X-User-Id'] = userId

  // 添加管理员标识（如果有）
  const isAdmin = localStorage.getItem('isAdmin') === 'true'
  if (isAdmin) {
    headers['X-Is-Admin'] = 'true'
  }

  const config = {
    ...options,
    method,
    headers
  }

  const response = await fetch(url, config)

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || `HTTP error! status: ${response.status}`)
  }

  // 204 No Content
  if (response.status === 204) {
    return null
  }

  return await response.json()
}

/**
 * 获取知识库列表
 */
export async function listKnowledgeBases() {
  return await request(BASE_URL)
}

/**
 * 创建知识库
 */
export async function createKnowledgeBase(params) {
  return await request(BASE_URL, {
    method: 'POST',
    body: JSON.stringify(params)
  })
}

/**
 * 获取知识库详情
 */
export async function getKnowledgeBase(id) {
  return await request(`${BASE_URL}/${id}`)
}

/**
 * 更新知识库
 */
export async function updateKnowledgeBase(id, params) {
  return await request(`${BASE_URL}/${id}`, {
    method: 'PUT',
    body: JSON.stringify(params)
  })
}

/**
 * 删除知识库
 */
export async function deleteKnowledgeBase(id) {
  return await request(`${BASE_URL}/${id}`, {
    method: 'DELETE'
  })
}

/**
 * 获取知识库统计
 */
export async function getKnowledgeBaseStats() {
  return await request(`${BASE_URL}/stats`)
}

/**
 * 获取分块策略列表
 */
export async function getChunkingStrategies() {
  return await request(`${BASE_URL}/strategies`)
}

/**
 * 上传文档
 * @param {string} kbId - 知识库ID
 * @param {File} file - 文件对象
 * @param {Object} options - 上传选项
 * @param {Object} options.metadata - 自定义元数据
 * @param {string} options.chunking_strategy - 分块策略 (sentence/semantic/markdown/hybrid/llm)
 * @param {number} options.chunk_size - 分块大小
 * @param {number} options.chunk_overlap - 分块重叠
 * @param {string} options.llm_mode - LLM模式 (local/online)，仅llm策略时有效
 */
export async function uploadDocument(kbId, file, options = {}) {
  const {
    metadata = {},
    chunking_strategy = 'llm',
    chunk_size = 800,
    chunk_overlap = 100,
    llm_mode = 'local'
  } = options

  const formData = new FormData()
  formData.append('file', file)
  formData.append('metadata', JSON.stringify(metadata))
  formData.append('chunking_strategy', chunking_strategy)
  formData.append('chunk_size', chunk_size.toString())
  formData.append('chunk_overlap', chunk_overlap.toString())
  formData.append('llm_mode', llm_mode)

  return await request(`${BASE_URL}/${kbId}/documents`, {
    method: 'POST',
    body: formData
  })
}

/**
 * 获取文档列表
 */
export async function listDocuments(kbId) {
  return await request(`${BASE_URL}/${kbId}/documents`)
}

/**
 * 删除文档
 */
export async function deleteDocument(kbId, docId) {
  return await request(`${BASE_URL}/${kbId}/documents/${docId}`, {
    method: 'DELETE'
  })
}

/**
 * 重试处理失败的文档
 */
export async function retryDocument(kbId, docId) {
  return await request(`${BASE_URL}/${kbId}/documents/${docId}/retry`, {
    method: 'POST'
  })
}

/**
 * 检索知识库
 */
export async function searchKnowledgeBase(params) {
  return await request(`${BASE_URL}/search`, {
    method: 'POST',
    body: JSON.stringify(params)
  })
}

/**
 * 获取文档分段
 */
export async function getDocumentChunks(kbId, docId) {
  return await request(`${BASE_URL}/${kbId}/documents/${docId}/chunks`)
}
