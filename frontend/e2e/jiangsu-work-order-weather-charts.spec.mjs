import { expect, test } from 'playwright/test'

// 故障工单审核工作台「气象时序」回归：站点全污染物（目标/对照/extra_points）+ 气象复合图，
// 与智能事件证据包对齐；小时时序图保持只画目标/对照。
const TIMES = ['2026-10-23 08:00:00', '2026-10-23 09:00:00', '2026-10-23 10:00:00']
const points = base => TIMES.map(time => ({ time, value: base }))
const stationHourSource = {
  source: 'station_hour',
  data: {
    unit: 'μg/m³', pollutant: 'NO', comparison_pollutant: 'NO2',
    points: points(20), comparison_points: points(30),
    extra_points: { PM10: points(50), 'PM2.5': points(35), SO2: points(8), CO: points(0.9), O3: points(60) },
  },
}
const weatherSource = {
  source: 'weather',
  data: { rows: TIMES.map(timePoint => ({ timePoint, windSpeed: 2.5, windDirection: 135, temperature: 22, humidity: 55, pressure: 1013 })) },
}
const empty = name => ({ source: name, data: null })
const entry = {
  working_order_code: 'FA-TEST', title: '测试故障工单', site_name: '测试站点',
  pollutant: 'NO', window_start: '2026-10-23 08:00:00', window_end: '2026-10-23 10:00:00',
  status: '待审核',
}
const index = {
  ...entry,
  mark_areas: [{ name: '异常时段', start: '2026-10-23 08:00:00', end: '2026-10-23 09:00:00', pollutant: 'NO' }],
  judgment: null, operations: [],
  sources: Object.fromEntries(['work_order', 'station_hour', 'band', 'weather', 'alarms', 'env_power', 'qc']
    .map(name => [name, { status: 'success', record_count: 6, summary: 'mock' }])),
}
const sourceByName = {
  station_hour: stationHourSource, weather: weatherSource,
  work_order: { source: 'work_order', data: { order: { orderTitle: '测试故障工单' }, attachments: [] } },
  band: empty('band'), alarms: empty('alarms'), env_power: empty('env_power'), qc: empty('qc'),
}

test('weather section renders every station pollutant beside weather series', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', route => {
    const { pathname } = new URL(route.request().url())
    if (pathname.endsWith('/work-order-reviews/FA-TEST/sources/weather')) return route.fulfill({ json: weatherSource })
    const sourceMatch = /\/work-order-reviews\/FA-TEST\/sources\/(\w+)$/.exec(pathname)
    if (sourceMatch) return route.fulfill({ json: sourceByName[sourceMatch[1]] || empty(sourceMatch[1]) })
    if (pathname.endsWith('/work-order-reviews/FA-TEST')) return route.fulfill({ json: { entry, index } })
    return route.fulfill({ json: { orders: [entry], statuses: ['待审核'], total: 1 } })
  })
  await page.route('**/__wor_weather_test__', route => route.fulfill({
    contentType: 'text/html',
    body: `<div id="app" style="height:900px"></div><script type="module">
      import { createApp, h, reactive } from '/node_modules/.vite/deps/vue.js'
      import Panel from '/src/components/management/WorkOrderReviewCenterPanel.vue'
      window.panelProps = reactive({ workspaceCommand: { type: 'open_work_order_review', working_order_code: 'FA-TEST' }, showListActions: false })
      window.panelApp = createApp({ render: () => h(Panel, window.panelProps) })
      window.panelApp.mount('#app')
    </script>`,
  }))
  await page.goto('/__wor_weather_test__')

  await expect(page.getByText('站点污染物与气象时序', { exact: true })).toBeVisible()
  await expect(page.locator('#wor-section-weather .weather-chart canvas')).toBeVisible()
  await expect(page.locator('#wor-section-station_hour canvas').first()).toBeVisible()

  const readCharts = () => page.evaluate(async () => {
    const echarts = await import('/node_modules/.vite/deps/echarts.js')
    const describe = holder => {
      const chart = echarts.getInstanceByDom(holder)
      if (!chart) return null
      const option = chart.getOption()
      return {
        seriesNames: option.series.map(item => item.name),
        seriesAxis: option.series.map(item => item.yAxisIndex),
        axisNames: option.yAxis.map(axis => axis.name || ''),
      }
    }
    return {
      weather: describe(document.querySelector('#wor-section-weather .weather-chart')),
      hourly: describe(document.querySelector('#wor-section-station_hour .chart-surface')),
    }
  })
  await expect.poll(() => readCharts().then(charts => charts.weather)).toEqual({
    seriesNames: ['NO（本站）', 'NO2（对照）', 'PM10（本站）', 'PM2.5（本站）', 'SO2（本站）', 'CO（本站）', 'O3（本站）',
      '风速 (m/s)', '风向', '温度 (°C)', '湿度 (%)', '大气压 (hPa)'],
    seriesAxis: [0, 0, 0, 0, 0, 1, 0, 2, 3, 4, 4, 5],
    axisNames: ['μg/m³', 'mg/m³', '风速 (m/s)', '', '温度/湿度', '气压 (hPa)'],
  })
  // 小时时序图保持聚焦：只有目标 + 对照两条污染物曲线
  await expect.poll(() => readCharts().then(charts => charts.hourly?.seriesNames)).toEqual(['NO（本站）', 'NO2（对照）'])
  expect(errors).toEqual([])
})
