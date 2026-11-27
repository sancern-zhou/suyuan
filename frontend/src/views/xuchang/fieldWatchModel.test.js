import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  IAQI_2026_1H,
  LEVEL_COLORS_2026,
  buildAlertView,
  buildCountyRows,
  buildForecastRows,
  buildTrend,
  dataClock,
  dayHourLabel,
  hourLabel,
  levelColor,
  levelDisplayColor,
  levelTextColor,
  pollutantLabel,
  pollutantLevelColor,
  pollutantLevelIndex,
  readableText,
  shadeColor,
  shortDateTime,
  tintColor
} from './fieldWatchModel.js'

/** 颜色与白底的对比度（WCAG） */
function contrastOnWhite(hex) {
  const channels = [1, 3, 5]
    .map(offset => parseInt(hex.slice(offset, offset + 2), 16) / 255)
    .map(s => (s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4))
  const luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
  return 1.05 / (luminance + 0.05)
}

test('分级表与项目权威表一致（backend/config/environment_chart_standards.json）', () => {
  const standards = JSON.parse(readFileSync(
    new URL('../../../../backend/config/environment_chart_standards.json', import.meta.url), 'utf8'))
  assert.deepEqual(LEVEL_COLORS_2026, standards.aqi_colors)
  const names = { so2: 'SO2', no2: 'NO2', co: 'CO', o3: 'O3', pm10: 'PM10', pm25: 'PM2.5' }
  assert.deepEqual(Object.keys(IAQI_2026_1H).sort(), Object.keys(names).sort())
  for (const [key, name] of Object.entries(names)) {
    assert.deepEqual(IAQI_2026_1H[key], standards.iaqi_2026[name]['1h'], `${key} 1 小时折点`)
  }
})

test('等级色取 HJ 633-2026 附录 A；缺测为灰', () => {
  assert.equal(levelColor(50), LEVEL_COLORS_2026[0])
  assert.equal(levelColor(101), LEVEL_COLORS_2026[2])
  assert.equal(levelColor(301), LEVEL_COLORS_2026[5])
  assert.equal(levelColor(null), '#5b7684')
  assert.equal(levelColor('x'), '#5b7684')
})

test('污染物按 1 小时折点定级：边界含上限，SO2 短表超出停在末档，浓度先修约', () => {
  // PM2.5：IAQI=100 落在 60（2026 版收严点）
  assert.deepEqual(
    [35, 36, 60, 61, 115, 116, 150, 151, 250, 251, 600].map(value => pollutantLevelIndex('pm25', value)),
    [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
  )
  assert.deepEqual(
    [150, 151, 500, 650, 800, 900, 5000].map(value => pollutantLevelIndex('so2', value)),
    [0, 1, 1, 2, 3, 3, 3]
  )
  assert.equal(pollutantLevelIndex('pm10', 120), 1)
  assert.equal(pollutantLevelIndex('PM10', 121), 2) // 键名大小写不敏感
  assert.equal(pollutantLevelIndex('o3', 200), 1)
  assert.equal(pollutantLevelIndex('no2', 200), 1)
  assert.equal(pollutantLevelIndex('co', 5), 0)
  assert.equal(pollutantLevelIndex('co', 5.1), 1)
  // 浓度先按标准修约再查表：PM2.5 60.4 → 60（良），不修约会落到轻度
  assert.equal(pollutantLevelIndex('pm25', 60.4), 1)
  assert.equal(pollutantLevelIndex('co', 10.04), 1)
  // 四舍六入五成双：前一位是奇数才进位
  assert.equal(pollutantLevelIndex('pm25', 34.5), 0) // 34 偶 → 34
  assert.equal(pollutantLevelIndex('pm25', 35.5), 1) // 35 奇 → 36
  assert.equal(pollutantLevelIndex('pm25', 60.5), 1) // 60 偶 → 60
  assert.equal(pollutantLevelIndex('pm25', 61.5), 2) // 61 奇 → 62
  assert.equal(pollutantLevelIndex('co', 10.05), 1) // 10.0 偶 → 10.0
  assert.equal(pollutantLevelIndex('co', 10.15), 2) // 10.1 奇 → 10.2
  // 缺测、负值、未知污染物不定级 → 灰
  assert.equal(pollutantLevelIndex('pm25', null), null)
  assert.equal(pollutantLevelIndex('pm25', -99), null)
  assert.equal(pollutantLevelIndex('o3_8h', 100), null)
  assert.equal(pollutantLevelColor('pm25', null), '#5b7684')
  assert.equal(pollutantLevelColor('pm25', 40), LEVEL_COLORS_2026[1])
})

test('白底文字色：纯黄/纯绿压暗到对比度达标，深色档保持原色', () => {
  for (const color of LEVEL_COLORS_2026) {
    assert.ok(contrastOnWhite(readableText(color)) >= 4.5, color)
    assert.ok(contrastOnWhite(readableText(color, 3)) >= 3, color)
  }
  assert.equal(readableText(LEVEL_COLORS_2026[4]), LEVEL_COLORS_2026[4])
  assert.equal(readableText(LEVEL_COLORS_2026[5]), LEVEL_COLORS_2026[5])
  assert.notEqual(readableText(LEVEL_COLORS_2026[1]), LEVEL_COLORS_2026[1])
  assert.notEqual(readableText(LEVEL_COLORS_2026[0]), LEVEL_COLORS_2026[0])
  // 大号数字比小字压暗得少，保留更多等级色
  assert.notEqual(levelDisplayColor(80), levelTextColor(80))
  assert.equal(levelTextColor(null), '#5b7684')
})

test('压暗/着色基础函数：非法输入有兜底', () => {
  assert.equal(shadeColor('#e5ae22', 0.25), '#ac831a')
  assert.equal(shadeColor('#21a366', 0), '#21a366')
  assert.equal(shadeColor('not-a-color'), '#5b7684')
  assert.equal(tintColor('#00E400', 0.12), 'rgba(0, 228, 0, 0.12)')
  assert.equal(tintColor('bad', 0.5), 'rgba(91, 118, 132, 0.5)')
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
  // 柱色随等级走附录 A：首柱 40 优、末柱 132 轻度
  assert.equal(trend.bars[0].color, LEVEL_COLORS_2026[0])
  assert.equal(trend.bars[23].color, LEVEL_COLORS_2026[2])
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

test('区县：默认按 AQI 升序、缺测排末尾、条形相对最大值归一', () => {
  const rows = buildCountyRows([
    { station_name: '魏都区', aqi: 58, quality: '良' },
    { station_name: '襄城县', aqi: 93, quality: '良' },
    { station_name: '鄢陵县', aqi: null, quality: '' },
    { station_name: '禹州市', aqi: 82, quality: '良' }
  ])
  assert.deepEqual(rows.map(row => row.name), ['魏都区', '禹州市', '襄城县', '鄢陵县'])
  // 最大值在最末，条形满格
  assert.equal(rows[2].widthPct, 100)
  assert.equal(rows[2].valueText, '93')
  assert.equal(rows[2].color, LEVEL_COLORS_2026[1])
  assert.equal(rows[0].level, '良')
  // 缺测：灰阶、占位符、无条形
  assert.equal(rows[3].valueText, '—')
  assert.equal(rows[3].widthPct, 0)
  assert.equal(rows[3].level, '—')
  assert.equal(rows[3].color, '#5b7684')
})

const COUNTY_FIXTURE = [
  { station_name: '魏都区', aqi: 58, pm25: 40, pm10: 71, o3: 96, so2: 7, no2: 31, co: 0.6 },
  { station_name: '建安区', aqi: 96, pm25: 69, pm10: 108, o3: 41, so2: 12, no2: 44, co: 0.9 },
  { station_name: '鄢陵县', aqi: 47, pm25: 20, pm10: null, o3: 132, so2: null, no2: 18, co: null },
  { station_name: '襄城县', aqi: 96, pm25: 69, pm10: 55, o3: 96, so2: 12, no2: 44, co: 0.9 }
]

test('区县：六项污染物均可选，按浓度升序，同值保持传入顺序，缺测排末尾', () => {
  const rows = buildCountyRows(COUNTY_FIXTURE, { metric: 'pm25' })
  assert.deepEqual(rows.map(row => row.name), ['鄢陵县', '魏都区', '建安区', '襄城县'])
  assert.deepEqual(rows.map(row => row.valueText), ['20', '40', '69', '69'])
  const pm10 = buildCountyRows(COUNTY_FIXTURE, { metric: 'pm10' })
  assert.deepEqual(pm10.map(row => row.name), ['襄城县', '魏都区', '建安区', '鄢陵县'])
  assert.equal(pm10[3].valueText, '—')
  assert.equal(pm10[3].levelColor, '#8a8f99')
})

test('区县：CO 保留一位小数，未知指标退回 AQI 升序', () => {
  const co = buildCountyRows(COUNTY_FIXTURE, { metric: 'co' })
  assert.deepEqual(co.map(row => row.valueText), ['0.6', '0.9', '0.9', '—'])
  const unknown = buildCountyRows(COUNTY_FIXTURE, { metric: 'o3_8h' })
  assert.deepEqual(unknown.map(row => row.name), ['鄢陵县', '魏都区', '建安区', '襄城县'])
  assert.equal(unknown[0].level, '优') // quality 缺失时由 AQI 定级（47）
})

test('区县：污染物按 2026 版 1 小时折点定色、副标注显示 AQI，缺测不落成"优"色', () => {
  const rows = buildCountyRows(COUNTY_FIXTURE, { metric: 'pm25' })
  // PM2.5 折点 35/60/115：20 优、40 良、69 轻度
  assert.deepEqual(rows.map(row => row.color), [
    LEVEL_COLORS_2026[0], LEVEL_COLORS_2026[1], LEVEL_COLORS_2026[2], LEVEL_COLORS_2026[2]
  ])
  assert.equal(rows[0].level, 'AQI 47')
  assert.equal(rows[0].textColor, readableText(LEVEL_COLORS_2026[0]))
  const missing = buildCountyRows([{ station_name: '鄢陵县', aqi: null, pm25: null }], { metric: 'pm25' })
  assert.equal(missing[0].color, '#5b7684')
  assert.equal(missing[0].level, 'AQI —')
  assert.equal(missing[0].valueText, '—')
})

test('区县：首要污染物按 AQI 升序列出，条形按 AQI，优级显示 —', () => {
  const rows = buildCountyRows([
    { station_name: '魏都区', aqi: 156, primary: 'PM10' },
    { station_name: '建安区', aqi: 47, primary: null },
    { station_name: '鄢陵县', aqi: 71, primary: 'PM2.5、PM10' },
    { station_name: '襄城县', aqi: 230, primary: 'o3' },
    { station_name: '长葛市', aqi: 63, primary: '-' },
    { station_name: '禹州市', aqi: null, primary: null }
  ], { metric: 'primary' })
  assert.deepEqual(rows.map(row => row.name), ['建安区', '长葛市', '鄢陵县', '魏都区', '襄城县', '禹州市'])
  // 多个首要污染物取首位；键名大小写归一；空值与占位符都显示 —
  assert.deepEqual(rows.map(row => row.valueText), ['—', '—', 'PM2.5', 'PM10', 'O3', '—'])
  assert.deepEqual(rows.map(row => row.level), ['AQI 47', 'AQI 63', 'AQI 71', 'AQI 156', 'AQI 230', 'AQI —'])
  // 47 优、63/71 良、156 中度、230 重度
  assert.deepEqual(rows.map(row => row.color), [
    LEVEL_COLORS_2026[0], LEVEL_COLORS_2026[1], LEVEL_COLORS_2026[1], LEVEL_COLORS_2026[3], LEVEL_COLORS_2026[4], '#5b7684'
  ])
  assert.equal(rows[4].widthPct, 100)
  assert.equal(rows[0].levelColor, '#8a8f99')
})

test('时间标注：页头保留分钟，区县标注到小时', () => {
  assert.equal(dataClock('2026-11-25T14:35:00.000'), '25日 14:35')
  assert.equal(dataClock('2026-11-25T14:00:00.000'), '25日 14:00')
  assert.equal(dataClock(''), '—')
  assert.equal(dayHourLabel('2026-11-25T14:00:00.000'), '25日 14时')
  assert.equal(dayHourLabel('2026-11-25 09:00:00'), '25日 9时')
  assert.equal(dayHourLabel(null), '')
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
  assert.equal(rows[1].color, LEVEL_COLORS_2026[2])
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
