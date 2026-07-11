const NODE_COLORS = ['#3996ae', '#5ad8a6', '#f6bd16', '#f27c7c', '#9581cc', '#6dc8ec', '#ff9d4d', '#92d050', '#e885ba']
const EDGE_COLORS = ['#99add1', '#3996ae', '#13c2c2', '#faad14', '#f27c7c', '#9581cc', '#52c41a', '#ff9d4d']

function hash(value) {
  let result = 0
  for (const character of String(value || '')) result = ((result << 5) - result + character.charCodeAt(0)) | 0
  return Math.abs(result)
}

export function stableTypeColor(type, palette = NODE_COLORS) {
  return palette[hash(type) % palette.length]
}

export function toG6Data(entities = [], relations = []) {
  const degrees = new Map(entities.map(entity => [String(entity.id), 0]))
  relations.forEach(relation => {
    const source = String(relation.source_entity_id)
    const target = String(relation.target_entity_id)
    degrees.set(source, (degrees.get(source) || 0) + 1)
    degrees.set(target, (degrees.get(target) || 0) + 1)
  })
  return {
    nodes: entities.map(entity => ({
      id: String(entity.id),
      data: {
        label: entity.name || entity.canonical_name || String(entity.id),
        type: entity.entity_type || 'Entity',
        color: stableTypeColor(entity.entity_type || 'Entity'),
        degree: degrees.get(String(entity.id)) || 0,
        original: entity
      }
    })),
    edges: relations.map((relation, index) => ({
      id: String(relation.id || `relation-${index}`),
      source: String(relation.source_entity_id),
      target: String(relation.target_entity_id),
      data: {
        label: relation.relation_type || 'RELATED_TO',
        type: relation.relation_type || 'RELATED_TO',
        color: stableTypeColor(relation.relation_type || 'RELATED_TO', EDGE_COLORS),
        original: relation
      }
    }))
  }
}

export function filterGraphData(graph, { entityTypes = new Set(), relationTypes = new Set() } = {}) {
  const nodes = graph.nodes.filter(node => !entityTypes.size || entityTypes.has(node.data.type))
  const visibleIds = new Set(nodes.map(node => node.id))
  const edges = graph.edges.filter(edge =>
    visibleIds.has(edge.source) && visibleIds.has(edge.target)
    && (!relationTypes.size || relationTypes.has(edge.data.type))
  )
  return { nodes, edges }
}

export function findEntityMatches(graph, query) {
  const normalized = String(query || '').trim().toLocaleLowerCase()
  if (!normalized) return []
  return graph.nodes
    .filter(node => {
      const entity = node.data.original || {}
      return [entity.name, entity.canonical_name, ...(entity.aliases || [])]
        .some(value => String(value || '').toLocaleLowerCase().includes(normalized))
    })
    .map(node => node.id)
}

export function neighborIds(graph, nodeId) {
  const ids = new Set([String(nodeId)])
  graph.edges.forEach(edge => {
    if (edge.source === String(nodeId)) ids.add(edge.target)
    if (edge.target === String(nodeId)) ids.add(edge.source)
  })
  return ids
}
