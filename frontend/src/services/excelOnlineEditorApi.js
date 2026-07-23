const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

function officeApiUrl(path, apiBaseUrl = API_BASE_URL) {
  const baseUrl = String(apiBaseUrl || '/api').replace(/\/$/, '')
  return `${baseUrl}/office/${path}`
}

export async function openExcelForEditing(filePath, fetchImpl = fetch, apiBaseUrl = API_BASE_URL) {
  if (!filePath) {
    throw new Error('缺少文档路径')
  }

  const response = await fetchImpl(officeApiUrl('open-excel', apiBaseUrl), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path: filePath })
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, '打开Excel文档失败'))
  }

  return await response.arrayBuffer()
}

export async function saveEditedExcel({
  filePath,
  sessionId = '',
  buffer,
  fileName = 'document.xlsx',
  fetchImpl = fetch,
  formDataFactory = () => new FormData(),
  apiBaseUrl = API_BASE_URL
}) {
  if (!filePath) {
    throw new Error('缺少文档路径')
  }
  if (!buffer) {
    throw new Error('缺少Excel内容')
  }

  const formData = formDataFactory()
  formData.append('file_path', filePath)
  formData.append('session_id', sessionId || '')
  formData.append(
    'file',
    new Blob([buffer], {
      type: getExcelMimeType(fileName)
    }),
    fileName || 'document.xlsx'
  )

  const response = await fetchImpl(officeApiUrl('save-excel', apiBaseUrl), {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, '保存Excel文档失败'))
  }

  const payload = await response.json()
  if (!payload?.success || !payload?.document) {
    throw new Error(payload?.message || '保存Excel文档失败')
  }

  return payload.document
}

export async function downloadExcelFile(filePath, {
  fallbackFileName = 'document.xlsx',
  fileName = fallbackFileName,
  fetchImpl = fetch,
  apiBaseUrl = API_BASE_URL
} = {}) {
  if (!filePath) {
    throw new Error('缺少文档路径')
  }

  const response = await fetchImpl(officeApiUrl('download-excel', apiBaseUrl), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      file_path: filePath,
      file_name: fileName || fallbackFileName
    })
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, '下载Excel文档失败'))
  }

  return {
    blob: await response.blob(),
    fileName: getResponseFilename(response, fallbackFileName)
  }
}

function getExcelMimeType(fileName) {
  return String(fileName || '').toLowerCase().endsWith('.xls')
    ? 'application/vnd.ms-excel'
    : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
}

function getResponseFilename(response, fallback) {
  const contentDisposition = response.headers?.get?.('Content-Disposition')
  if (!contentDisposition) {
    return fallback
  }

  const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1])
    } catch {
      return encodedMatch[1]
    }
  }

  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1] || fallback
}

async function readErrorMessage(response, fallback) {
  try {
    const payload = await response.json()
    return payload.detail || payload.message || fallback
  } catch (error) {
    try {
      return await response.text()
    } catch {
      return fallback
    }
  }
}
