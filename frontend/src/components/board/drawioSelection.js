const ATTR_PATTERN = /([\w:.-]+)\s*=\s*"([^"]*)"/g

const decodeXmlValue = (value = '') => {
  return String(value)
    .replace(/&#xa;/gi, '\n')
    .replace(/&#10;/g, '\n')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

const parseAttributes = (tag = '') => {
  const attrs = {}
  let match
  ATTR_PATTERN.lastIndex = 0
  while ((match = ATTR_PATTERN.exec(tag)) !== null) {
    attrs[match[1]] = decodeXmlValue(match[2])
  }
  return attrs
}

const toNumber = (value) => {
  if (value === undefined || value === null || value === '') return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const extractCellId = (cell) => {
  if (typeof cell === 'string' || typeof cell === 'number') return String(cell)
  if (!cell || typeof cell !== 'object') return ''
  return String(cell.id || cell.cell_id || cell.cellId || cell.mxCellId || '').trim()
}

const findCellXmlById = (xml, id) => {
  if (!xml || !id) return ''

  let cursor = 0
  while (cursor < xml.length) {
    const start = xml.indexOf('<mxCell', cursor)
    if (start === -1) return ''

    const tagEnd = xml.indexOf('>', start)
    if (tagEnd === -1) return ''

    const openTag = xml.slice(start, tagEnd + 1)
    if (!new RegExp(`\\bid\\s*=\\s*"${escapeRegExp(id)}"`).test(openTag)) {
      cursor = tagEnd + 1
      continue
    }

    if (/\/\s*>$/.test(openTag)) {
      return openTag
    }

    const close = xml.indexOf('</mxCell>', tagEnd + 1)
    if (close === -1) return ''
    return xml.slice(start, close + '</mxCell>'.length)
  }

  return ''
}

const parseGeometry = (cellXml) => {
  const geometryMatch = cellXml.match(/<mxGeometry\b[^>]*(?:\/>|>)/)
  if (!geometryMatch) return null

  const attrs = parseAttributes(geometryMatch[0])
  const geometry = {}

  for (const key of ['x', 'y', 'width', 'height']) {
    const numberValue = toNumber(attrs[key])
    if (numberValue !== undefined) geometry[key] = numberValue
  }

  if (attrs.relative !== undefined) {
    geometry.relative = attrs.relative === '1' || attrs.relative === 'true'
  }

  return Object.keys(geometry).length > 0 ? geometry : null
}

const parseCell = (cellXml, fallback = {}) => {
  const openTagMatch = cellXml.match(/<mxCell\b[^>]*(?:\/>|>)/)
  if (!openTagMatch) return fallback

  const attrs = parseAttributes(openTagMatch[0])
  const id = attrs.id || extractCellId(fallback)
  const geometry = parseGeometry(cellXml)

  return {
    ...fallback,
    id,
    value: attrs.value ?? fallback.value ?? '',
    vertex: attrs.vertex === '1' || attrs.vertex === 'true',
    edge: attrs.edge === '1' || attrs.edge === 'true',
    parent: attrs.parent ?? fallback.parent ?? null,
    source: attrs.source ?? fallback.source ?? null,
    target: attrs.target ?? fallback.target ?? null,
    style: attrs.style ?? fallback.style ?? '',
    geometry,
    xml: cellXml
  }
}

const normalizeSelectionPayload = (selection = []) => {
  if (Array.isArray(selection)) return selection
  if (typeof selection === 'string' || typeof selection === 'number') return [selection]
  if (!selection || typeof selection !== 'object') return []
  if (Array.isArray(selection.cells)) return selection.cells
  if (Array.isArray(selection.selected)) return selection.selected
  if (Array.isArray(selection.selection)) return selection.selection
  if (Array.isArray(selection.ids)) return selection.ids
  if (Array.isArray(selection.cellIds)) return selection.cellIds
  if (Array.isArray(selection.selectedIds)) return selection.selectedIds
  return extractCellId(selection) ? [selection] : []
}

export const parseDrawioSelectedCells = (currentXml = '', selection = []) => {
  const rawSelection = normalizeSelectionPayload(selection)
  const seen = new Set()
  const selected = []

  for (const rawCell of rawSelection) {
    const id = extractCellId(rawCell)
    if (!id || seen.has(id)) continue

    seen.add(id)
    const fallback = typeof rawCell === 'object' && rawCell !== null ? { ...rawCell, id } : { id }
    const cellXml = findCellXmlById(currentXml, id)
    selected.push(cellXml ? parseCell(cellXml, fallback) : fallback)
  }

  return selected
}

export const getDrawioSelectionPayload = (message = {}) => {
  return (
    message.cells ||
    message.selected ||
    message.selection ||
    message.ids ||
    message.cellIds ||
    message.selectedIds ||
    message.cell ||
    message.selectedCell ||
    []
  )
}

const parseExportJsonData = (data) => {
  if (!data) return null
  if (typeof data === 'object') return data
  if (typeof data !== 'string') return null

  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}

export const getDrawioSelectionPayloadFromExport = (message = {}) => {
  if (message.event !== 'export' || message.format !== 'json') return []

  const data = parseExportJsonData(message.data)
  const pages = Array.isArray(data?.pages) ? data.pages : []
  const ids = []

  for (const page of pages) {
    const cells = Array.isArray(page?.cells) ? page.cells : []
    for (const cell of cells) {
      const id = extractCellId(cell)
      if (!id || cell?.type === 'layer') continue
      ids.push(id)
    }
  }

  return ids
}
