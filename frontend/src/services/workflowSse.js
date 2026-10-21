export function parseSseChunk(buffer, onEvent) {
  const blocks = buffer.split(/\r?\n\r?\n/)
  const remainder = blocks.pop() || ''
  for (const block of blocks) {
    const data = block
      .split(/\r?\n/)
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n')
    if (!data) continue
    try { onEvent(data) } catch { /* Ignore malformed server events. */ }
  }
  return { remainder }
}

export function parseFinalSseData(buffer) {
  return buffer
    .split(/\r?\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trimStart())
    .join('\n')
}

