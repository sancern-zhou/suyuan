export async function collectGraphSnapshot(fetchPage, { statuses, signal, onProgress } = {}) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const entities = []
    const relations = []
    let cursor = null
    let snapshotVersion = null
    let entityTotal = 0
    let relationTotal = 0
    try {
      do {
        if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
        const page = await fetchPage({
          statuses: statuses || ['candidate', 'confirmed', 'published'],
          cursor,
          snapshotVersion,
          signal
        })
        snapshotVersion ??= page.snapshot_version
        entities.push(...(page.entities || []))
        relations.push(...(page.relations || []))
        entityTotal = page.entity_total || 0
        relationTotal = page.relation_total || 0
        cursor = page.next_cursor || null
        onProgress?.({
          loadedEntities: entities.length,
          loadedRelations: relations.length,
          entityTotal,
          relationTotal
        })
      } while (cursor)
      return { snapshotVersion, entities, relations, entityTotal, relationTotal }
    } catch (error) {
      const changed = error?.status === 409 || error?.code === 'graph_snapshot_changed'
      if (!changed || attempt === 1) throw error
    }
  }
  throw new Error('Unable to collect graph snapshot')
}
