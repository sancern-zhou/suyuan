import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'

const __dirname = dirname(fileURLToPath(import.meta.url))
const mapSource = readFileSync(resolve(__dirname, './GuangdongOverviewMap.vue'), 'utf8')
const loaderSource = readFileSync(resolve(__dirname, '../../utils/mapLoader.js'), 'utf8')
const boundarySource = readFileSync(resolve(__dirname, './guangdong-boundary.json'), 'utf8')

test('guangdong overview map focuses and masks non-Guangdong regions with AMap primitives', () => {
  const boundary = JSON.parse(boundarySource)
  assert.equal(boundary.type, 'FeatureCollection', 'local Guangdong boundary should be valid GeoJSON')
  assert.ok(boundary.features.length > 0, 'local Guangdong boundary should contain city features')
  assert.match(loaderSource, /'AMap\.DistrictSearch'/, 'AMap loader should include DistrictSearch plugin')
  assert.match(mapSource, /import guangdongBoundary/, 'map should import local Guangdong boundary data')
  assert.match(mapSource, /extractLocalGuangdongBoundaries/, 'map should extract local boundary fallback paths')
  assert.match(mapSource, /renderProvinceFocusWithBoundaries\(localBoundaries\)/, 'map should render local fallback boundaries when DistrictSearch is unavailable')
  assert.match(mapSource, /setZoomAndCenter\(\s*GUANGDONG_FOCUS_ZOOM,\s*GUANGDONG_CENTER/, 'map should explicitly focus Guangdong after initialization')
  assert.match(mapSource, /new AMapApi\.DistrictSearch\(/, 'map should query Guangdong district boundaries')
  assert.match(mapSource, /districtSearch\.search\(\s*'广东省'/, 'district query should target Guangdong province')
  assert.match(mapSource, /createGuangdongMaskPath/, 'map should build a province cutout mask path from local boundaries')
  assert.match(mapSource, /path:\s*createGuangdongMaskPath\(boundaries\)/, 'mask should use local Guangdong boundaries as cutout rings')
  assert.match(mapSource, /className:\s*'gd-province-mask'/, 'map should render non-Guangdong shadow masks')
  assert.match(mapSource, /zIndex:\s*60/, 'mask should be above base map tiles')
  assert.match(mapSource, /zIndex:\s*70/, 'province boundary should be above the shadow mask')
  assert.match(mapSource, /new AMapApi\.Polygon\(\{[\s\S]*?className:\s*'gd-province-boundary'/, 'map should render Guangdong boundary highlight polygons')
  assert.match(mapSource, /provinceOverlays/, 'province highlight overlays should be tracked for cleanup')
})
