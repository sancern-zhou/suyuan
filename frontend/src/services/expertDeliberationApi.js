const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function runExpertDeliberation(payload) {
  const response = await fetch(`${API_BASE_URL}/expert-deliberation/run`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function parseExpertDeliberationInputFiles(files) {
  const formData = new FormData()
  if (files.consultationFile) {
    formData.append('consultation_file', files.consultationFile)
  }
  if (files.monthlyReportFile) {
    formData.append('monthly_report_file', files.monthlyReportFile)
  }
  if (files.stage5ReportFile) {
    formData.append('stage5_report_file', files.stage5ReportFile)
  }

  const response = await fetch(`${API_BASE_URL}/expert-deliberation/parse-input-files`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function loadDefaultExpertDeliberationInputFiles() {
  const response = await fetch(`${API_BASE_URL}/expert-deliberation/default-input-files`)

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }

  return response.json()
}
