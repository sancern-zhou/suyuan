import { authFetch } from '../auth/http.js'

const spreadsheetMimeType = label => (
  String(label || '').toLowerCase().endsWith('.xls')
    ? 'application/vnd.ms-excel'
    : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)

export function coerceSpreadsheetCell(existing = {}, inputValue = '') {
  const value = String(inputValue ?? '')
  const next = { ...existing }
  delete next.w
  delete next.f

  if (value.startsWith('=') && value.length > 1) {
    delete next.v
    return { ...next, t: 'n', f: value.slice(1) }
  }
  if (existing.t === 'n' && value.trim() !== '' && Number.isFinite(Number(value))) {
    return { ...next, t: 'n', v: Number(value) }
  }
  if (existing.t === 'b' && /^(true|false)$/i.test(value)) {
    return { ...next, t: 'b', v: value.toLowerCase() === 'true' }
  }
  if (existing.t === 'd') {
    const date = new Date(value)
    if (!Number.isNaN(date.getTime())) return { ...next, t: 'd', v: date }
  }
  return { ...next, t: 's', v: value }
}

export async function saveSpreadsheetResource(resource, bytes, fetchImpl = authFetch) {
  const actionUrl = resource?.actions?.save
  if (!actionUrl) throw new Error('该表格不支持保存')
  const fileName = String(resource?.label || 'workbook.xlsx')
  const formData = new FormData()
  formData.append(
    'file',
    new Blob([bytes], { type: spreadsheetMimeType(fileName) }),
    fileName
  )
  const response = await fetchImpl(actionUrl, { method: 'POST', body: formData })
  if (!response.ok) {
    let message = ''
    try {
      const payload = await response.json()
      message = payload?.detail || payload?.message || ''
    } catch {
      message = await response.text()
    }
    throw new Error(message || `保存失败（HTTP ${response.status}）`)
  }
  const receipt = await response.json()
  if (!receipt?.success) throw new Error(receipt?.message || '保存失败')
  return receipt
}
