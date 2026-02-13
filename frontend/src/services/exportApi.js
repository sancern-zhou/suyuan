/**
 * 报告导出API服务
 * 
 * 支持导出PDF、Word、HTML格式的分析报告
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/**
 * 导出报告
 * @param {Object} data - 导出数据
 * @param {string} data.format - 导出格式: pdf/docx/html
 * @param {Object} data.report_content - 报告内容
 * @param {Array} data.charts - 图表列表（含用户状态和截图）
 * @returns {Promise<Object>} - 返回 { blob, fallback, originalFormat }
 */
export const exportReportApi = async (data) => {
  const response = await fetch(`${API_BASE}/api/export/report`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  })
  
  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`导出失败: ${response.status} - ${errorText}`)
  }
  
  const fallback = response.headers.get('X-Export-Fallback')
  const blob = await response.blob()
  
  return {
    blob,
    fallback,  // 如果PDF降级为HTML，这里是 "html"
    originalFormat: data.format
  }
}

/**
 * 检查导出服务状态
 * @returns {Promise<Object>} - 服务状态
 */
export const checkExportServiceStatus = async () => {
  try {
    const response = await fetch(`${API_BASE}/api/export/status`)
    if (!response.ok) {
      return { available: false, message: '服务不可用' }
    }
    return response.json()
  } catch (error) {
    return { available: false, message: error.message }
  }
}

export default {
  exportReportApi,
  checkExportServiceStatus
}
