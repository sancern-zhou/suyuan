const getRelationType = (relation) => relation?.relation_type || relation?.type || 'related_to'

const getRelationSourceId = (relation) => (
  relation?.source_entity_id || relation?.source || relation?.source_id || ''
)

const getRelationTargetId = (relation) => (
  relation?.target_entity_id || relation?.target || relation?.target_id || ''
)

const getRelationPairKey = (source, target) => [source, target].sort().join('__')

const getCurveness = (index, count) => {
  if (count <= 1) return 0
  const step = count > 3 ? 0.28 : 0.36
  return Number(((index - (count - 1) / 2) * step).toFixed(2))
}

const buildRelationLabel = (type, formatRelationType, showRelationLabels) => ({
  show: showRelationLabels,
  formatter: formatRelationType(type)
})

export function buildGraphLinks({
  relations,
  nodeIds,
  relationColorByType,
  isRelationTypeHidden,
  formatRelationType,
  showRelationLabels
}) {
  const visibleRelations = relations
    .map(relation => {
      const type = getRelationType(relation)
      const source = getRelationSourceId(relation)
      const target = getRelationTargetId(relation)
      if (isRelationTypeHidden(type) || !nodeIds.has(source) || !nodeIds.has(target)) return null
      return { relation, type, source, target }
    })
    .filter(Boolean)

  const selfLoopsBySource = new Map()
  const normalRelations = []

  visibleRelations.forEach(item => {
    if (item.source === item.target) {
      if (!selfLoopsBySource.has(item.source)) selfLoopsBySource.set(item.source, [])
      selfLoopsBySource.get(item.source).push(item)
    } else {
      normalRelations.push(item)
    }
  })

  const pairCounts = new Map()
  normalRelations.forEach(item => {
    const key = getRelationPairKey(item.source, item.target)
    pairCounts.set(key, (pairCounts.get(key) || 0) + 1)
  })

  const pairIndexes = new Map()
  const links = normalRelations.map(item => {
    const pairKey = getRelationPairKey(item.source, item.target)
    const pairIndex = pairIndexes.get(pairKey) || 0
    const pairTotal = pairCounts.get(pairKey) || 1
    pairIndexes.set(pairKey, pairIndex + 1)

    return {
      source: item.source,
      target: item.target,
      value: item.type,
      raw: item.relation,
      label: buildRelationLabel(item.type, formatRelationType, showRelationLabels),
      lineStyle: {
        color: relationColorByType.get(item.type) || '#64748b',
        width: 1.5,
        opacity: 0.68,
        curveness: getCurveness(pairIndex, pairTotal)
      }
    }
  })

  selfLoopsBySource.forEach((items, source) => {
    const first = items[0]
    links.push({
      source,
      target: source,
      value: 'self_loop_group',
      raw: {
        isSelfLoopGroup: true,
        source_entity_id: source,
        target_entity_id: source,
        source_name: first.relation.source_name || first.relation.target_name || source,
        target_name: first.relation.target_name || first.relation.source_name || source,
        relation_type: 'self_loop_group',
        selfLoopRelations: items.map(item => item.relation)
      },
      label: {
        show: true,
        formatter: `自关联 ${items.length} 条`
      },
      lineStyle: {
        color: relationColorByType.get(first.type) || '#64748b',
        width: 1.8,
        opacity: 0.72,
        curveness: 0.55
      }
    })
  })

  return links
}
