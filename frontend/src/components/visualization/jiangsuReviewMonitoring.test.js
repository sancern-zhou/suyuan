import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, reactive, ref } from 'vue'
import { finiteObservation, observationValue } from './reviewTimeSeriesData.js'

const { descriptor } = parse(readFileSync(new URL('./FaultWorkOrderReviewPanel.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'review-test', genDefaultAs: 'component' }).content
const dependencies = {
  computed, reactive, ref, onMounted: () => {}, watch: () => {},
  authFetch: () => { throw new Error('Unexpected network call') },
  finiteObservation, observationValue,
  AuthenticatedImage: {}, ImageLightbox: {}, ReviewTimeSeriesChart: {}, JiangsuWeatherReviewChart: {}
}
const component = new Function(...Object.keys(dependencies), script.replace(/^import .*$/gm, '') + '\nreturn component')(...Object.values(dependencies))
const dataset = value => ({ record_count: 1, data: [{ timePoint: '2026-09-01 00:00:00', sO2: value }] })
const setup = sop => component.setup({ data: { data: { review: { sop_id: sop, pollutants: ['SO2'] } } } }, { expose() {} })

for (const sop of ['SOP-01', 'SOP-02', 'SOP-03']) {
  test(`${sop} excludes archived audited datasets from monitoring and weather curves`, () => {
    const panel = setup(sop)
    panel.evidence.value = { monitoring: {
      station_5minute_raw: dataset(10), station_hour_raw: dataset(20),
      station_5minute_audited: dataset(999), station_hour_audited: dataset(999)
    } }
    assert.deepEqual(panel.monitoringEntries.value.map(entry => entry.key), ['station_5minute_raw', 'station_hour_raw'])
    assert.deepEqual(panel.monitoringEntries.value.map(entry => entry.series[0].points[0].value), [10, 20])
    assert.equal(panel.weatherMonitoringEntries.value[0].series.length, 1)
    assert.equal(panel.weatherMonitoringEntries.value[0].series[0].points[0].value, 20)
  })
}

test('district comparison follows distance order and excludes unrelated and audited records', () => {
  const panel = setup('SOP-02')
  panel.evidence.value = { same_city_monitoring: {
    comparison_scope: 'same_district', target_station_code: 'target', distance_ranking_complete: true,
    comparison_stations: [
      { station_code: 'near', station_name: '近站', distance_km: 1.2, is_nearest: true },
      { station_code: 'far', station_name: '远站', distance_km: 9.3 }
    ],
    station_hour_raw: { data: ['far', 'outside', 'target', 'near'].map(code => ({ ...dataset(20).data[0], code })) },
    station_hour_audited: dataset(999)
  } }
  const entries = panel.sameCityMonitoringEntries.value
  assert.equal(entries.length, 1)
  assert.deepEqual(entries[0].series.map(series => series.name), ['target（本站）', '近站 （同区最近） 1.20 km', '远站 9.30 km'])
  panel.evidence.value.same_city_monitoring.comparison_scope = 'same_city'
  assert.deepEqual(panel.sameCityMonitoringEntries.value, [])
  assert.match(panel.districtSelectionNote.value, /历史工单/)
})
