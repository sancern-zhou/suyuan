import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'

const __dirname = dirname(fileURLToPath(import.meta.url))
const mapSource = readFileSync(resolve(__dirname, './GuangdongOverviewMap.vue'), 'utf8')
const loaderSource = readFileSync(resolve(__dirname, '../../utils/mapLoader.js'), 'utf8')

test('guangdong overview map focuses and masks non-Guangdong regions with AMap primitives', () => {
  assert.match(loaderSource, /'AMap\.DistrictSearch'/, 'AMap loader should include DistrictSearch plugin')
  assert.match(mapSource, /setZoomAndCenter\(\s*GUANGDONG_FOCUS_ZOOM,\s*GUANGDONG_CENTER/, 'map should explicitly focus Guangdong after initialization')
  assert.match(mapSource, /new AMapApi\.DistrictSearch\(/, 'map should query Guangdong district boundaries')
  assert.match(mapSource, /districtSearch\.search\(\s*'广东省'/, 'district query should target Guangdong province')
  assert.match(mapSource, /createGuangdongMaskPath/, 'map should build a province cutout mask path')
  assert.match(mapSource, /new AMapApi\.Polygon\(\{[\s\S]*?className:\s*'gd-province-mask'/, 'map should render a non-Guangdong shadow mask')
  assert.match(mapSource, /new AMapApi\.Polygon\(\{[\s\S]*?className:\s*'gd-province-boundary'/, 'map should render Guangdong boundary highlight polygons')
  assert.match(mapSource, /provinceOverlays/, 'province highlight overlays should be tracked for cleanup')
})
