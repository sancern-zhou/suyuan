const visibleProgramLayers = (mapProgram) => Array.isArray(mapProgram?.state?.layers)
  ? mapProgram.state.layers.filter(layer => layer?.lifecycle?.visible !== false)
  : []

const layerDataId = (layer) => {
  if (layer?.data?.type === 'data_id') return layer.data.id || null
  if (layer?.data?.type === 'artifact_id') return layer.data.id || null
  return null
}

export function summarizeProgramLayerRenderResults(mapProgram, entries = []) {
  return visibleProgramLayers(mapProgram).map(layer => {
    const featureCount = entries.filter(entry => entry?.layer?.id === layer.id).length
    return {
      layer_id: layer.id,
      layer_type: layer.layer_type,
      data_id: layerDataId(layer),
      status: featureCount > 0 ? 'layer_rendered' : 'layer_empty',
      visible: true,
      feature_count: featureCount
    }
  })
}

export function createMapProgramExecutionReceipt(mapProgram, options = {}) {
  return {
    program_id: mapProgram?.program_id || null,
    status: options.status || 'executed',
    layers: Array.isArray(options.layers) ? options.layers : [],
    errors: Array.isArray(options.errors) ? options.errors : []
  }
}

