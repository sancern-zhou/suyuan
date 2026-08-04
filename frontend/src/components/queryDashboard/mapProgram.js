const VALID_LAYER_TYPES = new Set([
  'point',
  'line',
  'polygon',
  'heatmap',
  'raster_tile',
  'vector_tile',
  'trajectory',
  'wind_arrow',
  'label',
  'mask'
])

const DEFAULT_LIFECYCLE = {
  scope: 'turn',
  group: 'current_answer',
  visible: true,
  replace_policy: 'append',
  pinned: false
}

const DASHBOARD_LAYER_IDS = new Set(['city_metrics', 'stations', 'heatmap'])

const error = (path, message) => ({ path, message })

export function validateMapProgram(program) {
  const errors = []

  if (!program || typeof program !== 'object') {
    return { valid: false, errors: [error('', 'map program must be an object')] }
  }
  if (program.type !== 'map_program') errors.push(error('type', 'type must be map_program'))
  if (!program.program_id) errors.push(error('program_id', 'program_id is required'))
  if (!program.intent) errors.push(error('intent', 'intent is required'))
  if (!program.state || typeof program.state !== 'object') {
    errors.push(error('state', 'state is required'))
  }

  const layers = Array.isArray(program.state?.layers) ? program.state.layers : []
  const dashboardLayers = Array.isArray(program.state?.dashboard_layers) ? program.state.dashboard_layers : []
  layers.forEach((layer, index) => {
    const prefix = `state.layers[${index}]`
    if (!layer.id) errors.push(error(`${prefix}.id`, 'layer id is required'))
    if (!VALID_LAYER_TYPES.has(layer.layer_type)) {
      errors.push(error(`${prefix}.layer_type`, 'layer_type is not supported'))
    }
    if (!layer.data || typeof layer.data !== 'object') {
      errors.push(error(`${prefix}.data`, 'data reference is required'))
      return
    }
    if (!['file_path', 'artifact_id', 'inline_geojson'].includes(layer.data.type)) {
      errors.push(error(`${prefix}.data.type`, 'data.type must be file_path, artifact_id, or inline_geojson'))
    }
    if (layer.data.type === 'file_path' && !layer.data.path) {
      errors.push(error(`${prefix}.data.path`, 'data.path is required'))
    }
    if (layer.data.type === 'artifact_id' && !layer.data.id) {
      errors.push(error(`${prefix}.data.id`, 'data.id is required'))
    }
    if (layer.data.type === 'inline_geojson' && !Array.isArray(layer.data.features)) {
      errors.push(error(`${prefix}.data.features`, 'inline_geojson requires features array'))
    }
  })
  dashboardLayers.forEach((layer, index) => {
    const prefix = `state.dashboard_layers[${index}]`
    if (!DASHBOARD_LAYER_IDS.has(layer?.id)) {
      errors.push(error(`${prefix}.id`, 'dashboard layer id is not supported'))
    }
    if (typeof layer?.visible !== 'boolean') {
      errors.push(error(`${prefix}.visible`, 'visible must be boolean'))
    }
  })

  return { valid: errors.length === 0, errors }
}

export function normalizeMapProgram(program) {
  const validation = validateMapProgram(program)
  if (!validation.valid) {
    const first = validation.errors[0]
    throw new Error(`${first.path}: ${first.message}`)
  }

  return {
    type: 'map_program',
    version: program.version || '0.1',
    renderer: program.renderer || 'amap-compatible',
    program_id: program.program_id,
    intent: program.intent,
    state: {
      view: program.state?.view || {},
      layers: (program.state?.layers || []).map(layer => ({
        name: layer.name || layer.id,
        geometry: {},
        style: {},
        interactions: {},
        ...layer,
        lifecycle: {
          ...DEFAULT_LIFECYCLE,
          ...(layer.lifecycle || {})
        }
      })),
      dashboard_layers: (program.state?.dashboard_layers || []).map(layer => ({
        id: layer.id,
        visible: layer.visible
      }))
    },
    lineage: program.lineage || {}
  }
}
