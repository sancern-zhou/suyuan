export async function openDocxForEditing(filePath, fetchImpl = fetch) {
  if (!filePath) {
    throw new Error('缺少文档路径')
  }

  const response = await fetchImpl('/api/office/open-docx', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path: filePath })
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, '打开DOCX文档失败'))
  }

  return await response.arrayBuffer()
}

export async function saveEditedDocx({
  filePath,
  sessionId = '',
  buffer,
  fileName = 'document.docx',
  fetchImpl = fetch,
  formDataFactory = () => new FormData()
}) {
  if (!filePath) {
    throw new Error('缺少文档路径')
  }
  if (!buffer) {
    throw new Error('缺少DOCX内容')
  }

  const formData = formDataFactory()
  formData.append('file_path', filePath)
  formData.append('session_id', sessionId || '')
  formData.append(
    'file',
    new Blob([buffer], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }),
    fileName || 'document.docx'
  )

  const response = await fetchImpl('/api/office/save-docx', {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, '保存DOCX文档失败'))
  }

  const payload = await response.json()
  if (!payload?.success || !payload?.document) {
    throw new Error(payload?.message || '保存DOCX文档失败')
  }

  return payload.document
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
