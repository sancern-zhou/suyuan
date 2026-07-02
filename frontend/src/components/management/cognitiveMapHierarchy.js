const getEntityId = (entity) => entity?.entity_id || entity?.id || entity?.name || ''

const getRelationSourceId = (relation) => (
  relation?.source_entity_id || relation?.source || relation?.source_id || ''
)

const getRelationTargetId = (relation) => (
  relation?.target_entity_id || relation?.target || relation?.target_id || ''
)

const sortByName = (items) => (
  [...items].sort((left, right) => String(left.entity?.name || '').localeCompare(String(right.entity?.name || ''), 'zh-Hans-CN'))
)

export function buildEntityRelationTree(entities, relations) {
  const entityById = new Map()
  entities.forEach(entity => {
    const id = getEntityId(entity)
    if (id) entityById.set(id, entity)
  })

  const outgoing = new Map()
  const incomingIds = new Set()
  const connectedIds = new Set()

  relations.forEach(relation => {
    const sourceId = getRelationSourceId(relation)
    const targetId = getRelationTargetId(relation)
    if (!entityById.has(sourceId) || !entityById.has(targetId)) return
    if (!outgoing.has(sourceId)) outgoing.set(sourceId, [])
    outgoing.get(sourceId).push(relation)
    incomingIds.add(targetId)
    connectedIds.add(sourceId)
    connectedIds.add(targetId)
  })

  const makeNode = (entity, relation = null, path = []) => {
    const entityId = getEntityId(entity)
    const node = {
      id: entityId,
      entity,
      relation,
      cycle: path.includes(entityId),
      children: []
    }

    if (node.cycle) return node

    node.children = (outgoing.get(entityId) || [])
      .map(childRelation => {
        const target = entityById.get(getRelationTargetId(childRelation))
        return target ? makeNode(target, childRelation, [...path, entityId]) : null
      })
      .filter(Boolean)

    return node
  }

  let rootEntities = entities.filter(entity => {
    const id = getEntityId(entity)
    return connectedIds.has(id) && !incomingIds.has(id)
  })

  if (rootEntities.length === 0) {
    rootEntities = entities.filter(entity => connectedIds.has(getEntityId(entity))).slice(0, 1)
  }

  const orphans = entities
    .filter(entity => !connectedIds.has(getEntityId(entity)))
    .map(entity => makeNode(entity))

  return {
    roots: sortByName(rootEntities.map(entity => makeNode(entity))),
    orphans: sortByName(orphans)
  }
}

export function flattenEntityRelationTree(nodes, depth = 0) {
  return nodes.flatMap(node => [
    { ...node, depth },
    ...flattenEntityRelationTree(node.children || [], depth + 1)
  ])
}
