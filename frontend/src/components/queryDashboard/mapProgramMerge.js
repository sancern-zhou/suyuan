const asArray = (value) => Array.isArray(value) ? value : []

const lifecycleGroup = (item) => item?.lifecycle?.group || 'current_answer'

const mergeById = (existingItems = [], incomingItems = []) => {
  const merged = []
  const indexById = new Map()
  const replaceGroups = new Set(
    asArray(incomingItems)
      .filter(item => item?.lifecycle?.replace_policy === 'replace_group')
      .map(item => lifecycleGroup(item))
  )

  asArray(existingItems).forEach(item => {
    if (!item?.id) return
    if (replaceGroups.has(lifecycleGroup(item)) && !item.lifecycle?.pinned) return
    indexById.set(item.id, merged.length)
    merged.push(item)
  })

  asArray(incomingItems).forEach(item => {
    if (!item?.id) return
    if (indexById.has(item.id)) {
      merged[indexById.get(item.id)] = item
      return
    }
    indexById.set(item.id, merged.length)
    merged.push(item)
  })

  return merged
}

export function mergeMapPrograms(currentProgram, incomingProgram) {
  if (!currentProgram) return incomingProgram || null
  if (!incomingProgram) return currentProgram

  const currentState = currentProgram.state || {}
  const incomingState = incomingProgram.state || {}
  const hasIncomingView = Object.keys(incomingState.view || {}).length > 0

  return {
    ...currentProgram,
    ...incomingProgram,
    state: {
      ...currentState,
      ...incomingState,
      view: hasIncomingView ? incomingState.view : (currentState.view || {}),
      layers: mergeById(currentState.layers, incomingState.layers),
      dashboard_layers: mergeById(currentState.dashboard_layers, incomingState.dashboard_layers)
    },
    lineage: {
      ...(currentProgram.lineage || {}),
      ...(incomingProgram.lineage || {}),
      source_file_paths: [
        ...new Set([
          ...asArray(currentProgram.lineage?.source_file_paths),
          ...asArray(incomingProgram.lineage?.source_file_paths)
        ])
      ],
      dashboard_layer_ids: [
        ...new Set([
          ...asArray(currentProgram.lineage?.dashboard_layer_ids),
          ...asArray(incomingProgram.lineage?.dashboard_layer_ids)
        ])
      ]
    }
  }
}
