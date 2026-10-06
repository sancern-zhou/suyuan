import { formatTrajectoryValue } from './executionTrajectory.js'

export function mergeModelRecords(previous, latest) {
  const records = new Map(previous.map(record => [record.request_id, record]))
  for (const record of latest) records.set(record.request_id, record)
  return [...records.values()].sort((a, b) => a.request_id.localeCompare(b.request_id))
}

export function modelTrajectoryCards(records) {
  const histories = new Map()
  return records.map(record => {
    const request = record.request || {}
    const messages = request.messages || []
    const key = `${record.session_id}:${record.source}`
    const previous = histories.get(key)
    const conversational = ['main', 'subagent'].includes(record.source)
    // Compare the prefix, rather than only counts: compact/retry can replace history.
    const continuous = conversational && previous && messages.length >= previous.length
      && previous.every((message, index) => formatTrajectoryValue(message) === formatTrajectoryValue(messages[index]))
    const input = continuous ? messages.slice(previous.length).filter(message => message.role !== 'assistant') : messages
    if (conversational) histories.set(key, messages)
    const rows = []
    if (!continuous && request.system) rows.push({ role: 'system', kind: 'system', content: request.system })
    for (const message of input) {
      const blocks = Array.isArray(message.content) ? message.content : [{ type: 'text', text: message.content }]
      for (const block of blocks) rows.push(blockRow(block, message.role, 'input'))
      for (const call of message.tool_calls || []) rows.push({ role: 'assistant', kind: 'tool', section: 'input', content: call })
    }
    for (const block of record.response?.content || []) rows.push(blockRow(block, 'assistant', 'output'))
    if (request.tools?.length) rows.push({ role: 'system', kind: 'tools', section: 'input', content: request.tools })
    return { ...record, rows: rows.map((row, index) => ({ ...row, id: `${record.request_id}:${index}`, text: formatTrajectoryValue(row.content) })) }
  })
}

function blockRow(block, role, section) {
  const kind = block.type === 'thinking' ? 'thinking' : ['tool_use', 'tool_result'].includes(block.type) ? 'tool' : role
  return { role: block.type === 'tool_result' ? 'tool' : role, kind, section,
    title: block.name || block.tool_use_id || '',
    content: block.type === 'text' ? block.text : block.type === 'thinking' ? block.thinking : block }
}

export function trajectoryUsage(record) {
  const usage = record.response?.usage || {}
  const input = Number(usage.input_tokens || 0)
  const output = Number(usage.output_tokens || 0)
  const cached = Number(usage.cache_read_input_tokens || 0)
  const cacheWrite = Number(usage.cache_creation_input_tokens || 0)
  // Anthropic's input_tokens exclude cache counts; chat adapters include them.
  const total = input + output + (record.token_usage_mode === 'anthropic' ? cached + cacheWrite : 0)
  return { input, output, cached, cacheWrite, total }
}
