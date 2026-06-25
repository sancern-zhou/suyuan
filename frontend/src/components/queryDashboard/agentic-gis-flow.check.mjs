import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { normalizeMapProgram } from './mapProgram.js'
import { createMapEvent } from './mapEventBridge.js'
import { layerStateFromMapProgram } from './mapProgramDashboardLayers.js'

const program = normalizeMapProgram({
  type: 'map_program',
  version: '0.1',
  program_id: 'mapprog_demo',
  intent: 'Demo high station layer',
  state: {
    view: { fit_bounds: true },
    layers: [
      {
        id: 'demo_high_station',
        name: 'Demo high station',
        layer_type: 'point',
        data: {
          type: 'inline_geojson',
          features: [
            {
              type: 'Feature',
              geometry: { type: 'Point', coordinates: [113.26, 23.13] },
              properties: { station_name: 'demo', pm25: 88 }
            }
          ]
        },
        geometry: { type: 'point' },
        style: { type: 'classified', field: 'pm25' }
      }
    ]
  }
})

assert.equal(program.state.layers[0].lifecycle.scope, 'turn')

const contourProgram = normalizeMapProgram({
  type: 'map_program',
  version: '0.1',
  program_id: 'mapprog_pm25_contours',
  intent: 'Render PM2.5 interpolation contours',
  state: {
    view: { fit_bounds: true },
    layers: [
      {
        id: 'pm25_interpolation_contours',
        name: 'PM2.5 interpolation contours',
        layer_type: 'line',
        data: {
          type: 'inline_geojson',
          features: [
            {
              type: 'Feature',
              geometry: { type: 'LineString', coordinates: [[113.0, 23.0], [113.01, 23.01]] },
              properties: { level: 35 }
            }
          ]
        },
        geometry: { type: 'geojson', geometry_field: 'geometry' },
        style: { stroke_color: '#d7191c', stroke_weight: 2 }
      }
    ]
  }
})

assert.equal(contourProgram.state.layers[0].layer_type, 'line')
assert.equal(contourProgram.state.layers[0].style.stroke_color, '#d7191c')

const surfaceProgram = normalizeMapProgram({
  type: 'map_program',
  version: '0.1',
  program_id: 'mapprog_pm25_surface',
  intent: 'Render PM2.5 interpolation surface',
  state: {
    view: { fit_bounds: true },
    layers: [
      {
        id: 'pm25_interpolation_surface',
        name: 'PM2.5 interpolation surface',
        layer_type: 'polygon',
        data: {
          type: 'inline_geojson',
          features: [
            {
              type: 'Feature',
              geometry: {
                type: 'Polygon',
                coordinates: [[[113, 23], [113.01, 23], [113.01, 23.01], [113, 23.01], [113, 23]]]
              },
              properties: { value: 35, fill_color: '#fee08b', fill_opacity: 0.58 }
            }
          ]
        },
        geometry: { type: 'geojson', geometry_field: 'geometry' },
        style: {
          type: 'interpolation_surface',
          feature_fill_color_field: 'fill_color',
          feature_fill_opacity_field: 'fill_opacity'
        }
      }
    ]
  }
})

assert.equal(surfaceProgram.state.layers[0].layer_type, 'polygon')
assert.equal(surfaceProgram.state.layers[0].style.type, 'interpolation_surface')

const mapSource = readFileSync(new URL('./GuangdongOverviewMap.vue', import.meta.url), 'utf8')
assert.match(mapSource, /feature_fill_color_field/)
assert.match(mapSource, /feature_fill_opacity_field/)
assert.match(mapSource, /fit_bounds/)
assert.match(mapSource, /setFitView/)
assert.match(mapSource, /programOverlays/)

const dashboardLayerProgram = normalizeMapProgram({
  type: 'map_program',
  version: '0.1',
  program_id: 'mapprog_dashboard_stations',
  intent: 'Show station dashboard layer',
  state: {
    dashboard_layers: [
      { id: 'stations', visible: true },
      { id: 'heatmap', visible: false }
    ],
    layers: []
  }
})

assert.deepEqual(dashboardLayerProgram.state.dashboard_layers, [
  { id: 'stations', visible: true },
  { id: 'heatmap', visible: false }
])
assert.deepEqual(layerStateFromMapProgram(dashboardLayerProgram), {
  city_metrics: false,
  stations: true,
  heatmap: false
})

const event = createMapEvent('draw_completed', {
  sessionId: 'query_demo',
  geometry: { type: 'Polygon', coordinates: [[[113, 23], [114, 23], [114, 24], [113, 23]]] },
  activeLayers: [program.state.layers[0].id],
  now: () => new Date('2026-06-23T02:00:00.000Z')
})

assert.equal(event.event, 'draw_completed')
assert.deepEqual(event.active_layers, ['demo_high_station'])
