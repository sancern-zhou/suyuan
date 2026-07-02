import { fetchMapDataFeatures as defaultFetchMapDataFeatures } from '../../api/queryDashboard.js'

export async function loadProgramLayerFeatures(layer, options = {}) {
  if (!['point', 'polygon', 'line'].includes(layer?.layer_type)) return []
  if (layer?.lifecycle?.visible === false) return []

  if (layer?.data?.type === 'inline_geojson') {
    return Array.isArray(layer.data.features) ? layer.data.features : []
  }

  if (layer?.data?.type !== 'data_id' || !layer.data.id) return []

  const fetchMapDataFeatures = options.fetchMapDataFeatures || defaultFetchMapDataFeatures
  const requestOptions = {
    view: layer.data.view,
    limit: layer.data.limit
  }

  if (layer.layer_type === 'point') {
    const longitudeField = layer.geometry?.longitude_field || layer.geometry?.lon || layer.geometry?.x
    const latitudeField = layer.geometry?.latitude_field || layer.geometry?.lat || layer.geometry?.y
    if (!longitudeField || !latitudeField) return []
    requestOptions.lon = longitudeField
    requestOptions.lat = latitudeField
  }

  const result = await fetchMapDataFeatures(layer.data.id, requestOptions)
  return Array.isArray(result?.features) ? result.features : []
}

export async function loadProgramPointFeatures(layer, options = {}) {
  if (layer?.layer_type !== 'point') return []
  return await loadProgramLayerFeatures(layer, options)
}

export async function loadProgramPointFeatureEntries(mapProgram, options = {}) {
  const programLayers = Array.isArray(mapProgram?.state?.layers)
    ? mapProgram.state.layers
    : []

  const entries = []
  for (const layer of programLayers) {
    const features = await loadProgramPointFeatures(layer, options)
    features.forEach(feature => entries.push({ layer, feature }))
  }
  return entries
}

export async function loadProgramLayerFeatureEntries(mapProgram, options = {}) {
  const programLayers = Array.isArray(mapProgram?.state?.layers)
    ? mapProgram.state.layers
    : []

  const entries = []
  for (const layer of programLayers) {
    const features = await loadProgramLayerFeatures(layer, options)
    features.forEach(feature => entries.push({ layer, feature }))
  }
  return entries
}
