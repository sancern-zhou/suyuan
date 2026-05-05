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

export async function runExpertDeliberationStream(payload, { onEvent, signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/expert-deliberation/run-stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload),
    signal
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }
  if (!response.body) {
    throw new Error('会商进度流为空')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalResult = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''

    for (const eventText of events) {
      const dataLine = eventText
        .split('\n')
        .find(line => line.startsWith('data: '))
      if (!dataLine) continue
      const event = JSON.parse(dataLine.slice(6))
      if (event.event === 'result') {
        finalResult = event.result
      }
      if (event.event === 'error') {
        throw new Error(event.message || '会商生成失败')
      }
      onEvent?.(event)
    }
  }

  return finalResult
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

export async function listExpertDeliberationRuns(limit = 30) {
  const response = await fetch(`${API_BASE_URL}/expert-deliberation/runs?limit=${encodeURIComponent(limit)}`)

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function getExpertDeliberationRun(runId) {
  const response = await fetch(`${API_BASE_URL}/expert-deliberation/runs/${encodeURIComponent(runId)}`)

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }

  return response.json()
}
