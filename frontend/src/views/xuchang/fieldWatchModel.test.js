import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  buildAlertView,
  buildCountyRows,
  buildForecastRows,
  buildTrend,
  hourLabel,
  levelDisplayColor,
  levelTextColor,
  pollutantLabel,
  shadeColor,
  shortDateTime,
  tintColor
} from './fieldWatchModel.js'

test('等级色压暗/着色：浅色底上保持可读，非法输入有兜底', () => {
  assert.equal(shadeColor('#e5ae22', 0.25), '#ac831a')
  assert.equal(shadeColor('#21a366', 0), '#21a366')
  assert.equal(shadeColor('not-a-color'), '#5b7684')
  assert.equal(tintColor('#21a366', 0.12), 'rgba(33, 163, 102, 0.12)')
  assert.equal(levelTextColor(null), '#445963') // 缺测灰同样压暗
  // 大号数字比小字少压暗，保留等级色辨识度
  assert.notEqual(levelDisplayColor(80), levelTextColor(80))
})

test('污染物键名转展示标签', () => {
  assert.equal(pollutantLabel('pm25'), 'PM2.5')
  assert.equal(pollutantLabel('PM10'), 'PM10')
  assert.equal(pollutantLabel('o3'), 'O3')
  assert.equal(pollutantLabel(''), '')
  assert.equal(pollutantLabel(null), '')
})

test('时间格式化：非法输入不抛异常', () => {
  assert.equal(shortDateTime('2026-11-25T13:40:00'), '11-25 13:40')
  assert.equal(shortDateTime(''), '—')
  assert.equal(hourLabel('2026-11-25T05:00:00'), '5时')
  assert.equal(hourLabel(undefined), '')
})

test('趋势图：柱子几何、网格线与刻度', () => {
  const rows = Array.from({ length: 24 }, (_, i) => ({
    data_time: `2026-11-25T${String(i).padStart(2, '0')}:00:00`,
    aqi: 40 + i * 4
  }))
  const trend = buildTrend(rows)
  assert.equal(trend.bars.length, 24)
  assert.equal(trend.yMax, 150)
  assert.ok(trend.grid.some(line => line.value === 100 && line.dashed))
  // 柱子全部落在绘图区内且高度随 AQI 单调
  for (const bar of trend.bars) {
    assert.ok(bar.y >= 0 && bar.y + bar.height <= trend.baseline + 0.001)
    assert.ok(bar.width > 0)
  }
  assert.ok(trend.bars[23].y < trend.bars[0].y)
  // 刻度含首、末小时
  assert.equal(trend.ticks[0].label, '0时')
  assert.equal(trend.ticks[trend.ticks.length - 1].label, '23时')
})

test('趋势图：缺测小时留空、空数据返回 null', () => {
  const trend = buildTrend([
    { data_time: '2026-11-25T00:00:00', aqi: 60 },
    { data_time: '2026-11-25T01:00:00', aqi: null },
    { data_time: '2026-11-25T02:00:00', aqi: 80 }
  ])
  assert.equal(trend.bars.length, 2)
  // 缺测不改变后续柱子的槽位
  assert.ok(trend.bars[1].x > trend.bars[0].x * 2)
  assert.equal(buildTrend([]), null)
  assert.equal(buildTrend(undefined), null)
})

test('区县：按 AQI 降序、缺测排末尾、条形相对最大值归一', () => {
  const rows = buildCountyRows([
    { station_name: '魏都区', aqi: 58, quality: '良' },
    { station_name: '襄城县', aqi: 93, quality: '良' },
    { station_name: '鄢陵县', aqi: null, quality: '' },
    { station_name: '禹州市', aqi: 82, quality: '良' }
  ])
  assert.deepEqual(rows.map(row => row.name), ['襄城县', '禹州市', '魏都区', '鄢陵县'])
  assert.equal(rows[0].widthPct, 100)
  assert.equal(rows[3].aqiText, '—')
  assert.equal(rows[3].widthPct, 0)
  assert.equal(rows[3].level, '—')
})

test('预报：今天/明天标注、区间段定位与定级取区间上限', () => {
  const rows = buildForecastRows([
    { date: '2026-11-25', min_aqi: 45, max_aqi: 75, primary_pollutant: 'PM2.5' },
    { date: '2026-11-26', min_aqi: 80, max_aqi: 120, primary_pollutant: 'pm25' },
    { date: '2026-11-27', min_aqi: null, max_aqi: null, aqi: null }
  ], new Date('2026-11-25T09:00:00'))
  assert.equal(rows[0].weekday, '今天')
  assert.equal(rows[1].weekday, '明天')
  assert.equal(rows[0].rangeText, '45~75')
  assert.equal(rows[0].leftPct, 30)
  assert.equal(rows[0].widthPct, 20)
  assert.equal(rows[1].level, '轻度污染')
  assert.equal(rows[1].primary, 'PM2.5')
  assert.equal(rows[2].rangeText, '—')
  assert.equal(rows[2].widthPct, 0)
  assert.deepEqual(buildForecastRows([]), [])
})

test('预报：缺区间端点时退化为单值', () => {
  const rows = buildForecastRows([
    { date: '2026-11-25', min_aqi: null, max_aqi: null, aqi: 66 }
  ], new Date('2026-11-25T09:00:00'))
  assert.equal(rows[0].rangeText, '66~66')
  assert.equal(rows[0].widthPct, 3)
})

test('告警：指标片段、起止时间与状态', () => {
  const view = buildAlertView({
    episode_id: 'ep-1',
    station_name: '市监测站',
    target_pollutant: 'pm25',
    status: 'active',
    started_at: '2026-11-25T11:00:00',
    last_seen_at: '2026-11-25T14:00:00',
    hour_count: 4,
    peak_station_value: 118,
    peak_deviation_ratio: 1.8
  })
  assert.equal(view.active, true)
  assert.equal(view.statusText, '进行中')
  assert.equal(view.pollutant, 'PM2.5')
  assert.deepEqual(view.metrics.map(metric => metric.label), ['峰值', '偏离周边', '已持续'])
  assert.equal(view.timeText, '11-25 11:00 起 · 最近 14:00')
  // 快照未回挂派发通报（无 dispatch 字段）时行不可展开
  assert.equal(view.notice, null)

  const closed = buildAlertView({ station_id: 'xc_021', status: 'closed' })
  assert.equal(closed.active, false)
  assert.equal(closed.statusText, '已结束')
  assert.equal(closed.name, 'xc_021')
  assert.deepEqual(closed.metrics, [])
  assert.equal(closed.timeText, '')
  assert.equal(closed.notice, null)
})

test('告警：派发通报随 dispatch 回挂，正文保留换行、空正文视为无通报', () => {
  const view = buildAlertView({
    episode_id: 'ep-1',
    station_name: '市监测站',
    status: 'active',
    dispatch: {
      time: '2026-11-25T13:05:00',
      text: '【浓度告警】1.告警站点：市监测站\n2.污染指标：PM2.5\n3.告警情况：峰值118μg/m³'
    }
  })
  assert.equal(view.notice.time, '11-25 13:05')
  assert.ok(view.notice.text.includes('\n'))
  assert.ok(view.notice.text.startsWith('【浓度告警】'))

  // 通报正文为空（任务尚未完成或查库降级）不产出 notice，行不可点
  assert.equal(buildAlertView({ status: 'active', dispatch: { time: '2026-11-25T13:05:00', text: '  ' } }).notice, null)
  assert.equal(buildAlertView({ status: 'active', dispatch: {} }).notice, null)
  assert.equal(buildAlertView({ status: 'active', dispatch: null }).notice, null)
})
