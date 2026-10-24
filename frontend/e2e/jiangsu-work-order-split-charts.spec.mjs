import { expect, test } from 'playwright/test'

// 故障工单审核工作台「污染物小时时序」按污染物拆图回归：
// 多目标污染物时每个污染物一张图（本站 + 配对对照 + 它自己的剔除区间），
// 避免同图叠加时目标/对照曲线与剔除区间互相遮挡；同城对比带只随主目标图。
const TIMES = ['2026-10-23 08:00:00', '2026-10-23 09:00:00', '2026-10-23 10:00:00']
const points = base => TIMES.map(time => ({ time, value: base }))
const band = TIMES.map(time => ({ time, target: 20, min: 15, median: 18, max: 26 }))
const stationHourSource = {
  source: 'station_hour',
  data: {
    unit: 'μg/m³', pollutant: 'NO', comparison_pollutant: 'NO2', pollutants: ['NO', 'O3'],
    points: points(20), comparison_points: points(30),
    extra_points: { O3: points(60), CO: points(0.9) },
  },
}
const empty = name => ({ source: name, data: null })
const entry = {
  working_order_code: 'FA-SPLIT', title: '多污染物测试工单', site_name: '测试站点',
  pollutant: 'NO', window_start: '2026-10-23 08:00:00', window_end: '2026-10-23 10:00:00',
  status: '待审核',
}
const index = {
  ...entry,
  mark_areas: [
    { name: 'NO剔除区间', pollutant: 'NO', start: '2026-10-23 08:00:00', end: '2026-10-23 09:00:00' },
    { name: 'NO2剔除区间', pollutant: 'NO2', start: '2026-10-23 08:00:00', end: '2026-10-23 09:00:00' },
    { name: 'O3剔除区间', pollutant: 'O3', start: '2026-10-23 09:00:00', end: '2026-10-23 10:00:00' },
    { name: '剔除候选', start: '2026-10-23 08:30:00', end: '2026-10-23 09:30:00' },
  ],
  judgment: null, operations: [],
  sources: Object.fromEntries(['work_order', 'station_hour', 'band', 'weather', 'alarms', 'env_power', 'qc']
    .map(name => [name, { status: 'success', record_count: 6, summary: 'mock' }])),
}
const sourceByName = {
  station_hour: stationHourSource,
  band: { source: 'band', data: { band, district_name: '测试区' } },
  weather: empty('weather'),
  work_order: { source: 'work_order', data: { order: { orderTitle: '多污染物测试工单' }, attachments: [] } },
  alarms: empty('alarms'), env_power: empty('env_power'), qc: empty('qc'),
}

test('multi-pollutant hourly series split into one chart per pollutant', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', route => {
    const { pathname } = new URL(route.request().url())
    if (pathname.endsWith('/work-order-reviews/FA-SPLIT')) return route.fulfill({ json: { entry, index } })
    const sourceMatch = /\/work-order-reviews\/FA-SPLIT\/sources\/(\w+)$/.exec(pathname)
    if (sourceMatch) return route.fulfill({ json: sourceByName[sourceMatch[1]] || empty(sourceMatch[1]) })
    return route.fulfill({ json: { orders: [entry], statuses: ['待审核'], total: 1 } })
  })
  await page.route('**/__wor_split_test__', route => route.fulfill({
    contentType: 'text/html',
    body: `<div id="app" style="height:900px"></div><script type="module">
      import { createApp, h, reactive } from '/node_modules/.vite/deps/vue.js'
      import Panel from '/src/components/management/WorkOrderReviewCenterPanel.vue'
      window.panelProps = reactive({ workspaceCommand: { type: 'open_work_order_review', working_order_code: 'FA-SPLIT' }, showListActions: false })
      window.panelApp = createApp({ render: () => h(Panel, window.panelProps) })
      window.panelApp.mount('#app')
    </script>`,
  }))
  await page.goto('/__wor_split_test__')

  // 拆图标题：NO / NO2 / O3 各一张
  await expect(page.locator('#wor-section-station_hour')).toBeVisible()
  await expect(page.getByText('NO 小时时序', { exact: true })).toBeVisible()
  await expect(page.getByText('NO2 小时时序', { exact: true })).toBeVisible()
  await expect(page.getByText('O3 小时时序', { exact: true })).toBeVisible()

  const readCharts = () => page.evaluate(async () => {
    const echarts = await import('/node_modules/.vite/deps/echarts.js')
    return [...document.querySelectorAll('#wor-section-station_hour .chart-surface')].map(holder => {
      const chart = echarts.getInstanceByDom(holder)
      if (!chart) return null
      const option = chart.getOption()
      const areas = (option.series[0]?.markArea?.data || [])
        .map(pair => String(pair[0]?.name || '').split('\n')[0])
      return {
        seriesNames: option.series.map(item => item.name),
        seriesColors: option.color,
        markAreaNames: areas,
      }
    })
  })

  await expect.poll(readCharts).toHaveLength(3)
  const charts = (await readCharts()).filter(Boolean)
  // 主目标图：NO 本站 + NO2 对照 + 同城带三条；归属 NO 与无归属的区间都落在这张图
  assertChart(charts[0], {
    series: ['NO（本站）', 'NO2（对照）', '同城最低', '同城中位', '同城最高'],
    areas: ['NO剔除区间', '剔除候选'],
  })
  // 包内对照污染物被剔除 → 自己的图，配对翻转为 NO 对照
  assertChart(charts[1], { series: ['NO2（本站）', 'NO（对照）'], areas: ['NO2剔除区间'] })
  // 其余目标污染物图：O3 本站 + NO2 对照
  assertChart(charts[2], { series: ['O3（本站）', 'NO2（对照）'], areas: ['O3剔除区间'] })
  // 同一污染物跨图同色（NO2 在主图为对照紫、在 O3 图仍为紫）
  const no2ColorMain = charts[0].seriesColors[charts[0].seriesNames.indexOf('NO2（对照）')]
  const no2ColorO3 = charts[2].seriesColors[charts[2].seriesNames.indexOf('NO2（对照）')]
  expect(no2ColorMain).toBe(no2ColorO3)
  expect(errors).toEqual([])
})

function assertChart(chart, { series, areas }) {
  expect(chart.seriesNames).toEqual(series)
  expect(chart.markAreaNames).toEqual(areas)
}
