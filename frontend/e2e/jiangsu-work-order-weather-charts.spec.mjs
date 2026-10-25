import { expect, test } from 'playwright/test'

// 故障工单审核工作台「气象时序」回归：右上角污染物切换器（参照智能事件对比图），
// 一次只画选中污染物的本站+配对对照曲线；轴收紧到实际观测范围，不留未来空段。
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
  pollutant: 'NO',
  // 窗口是创建自然日（末端在未来），数据只到 10:00：轴须收紧到观测范围，不留未来空段。
  window_start: '2026-10-23 08:00:00', window_end: '2026-10-23 23:59:59',
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

test('weather section switches pollutants and clamps axis to observed range', async ({ page }) => {
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
  const switchGroup = page.getByRole('group', { name: '气象图污染物切换' })
  // 互为配对的污染物并成一组：PM10/PM2.5、NO/NO2；单向配对 O3 与无配对 SO2/CO 独立
  await expect(switchGroup.getByRole('button')).toHaveCount(5)

  const readWeather = () => page.evaluate(async () => {
    const echarts = await import('/node_modules/.vite/deps/echarts.js')
    const holder = document.querySelector('#wor-section-weather .weather-chart')
    const chart = echarts.getInstanceByDom(holder)
    if (!chart) return null
    const option = chart.getOption()
    return {
      seriesNames: option.series.map(item => item.name),
      seriesAxis: option.series.map(item => item.yAxisIndex),
      axisNames: option.yAxis.map(axis => axis.name || ''),
      axisRange: { min: option.xAxis[0].min, max: option.xAxis[0].max },
      pollutantSlotCount: option.series[0].data.length,
      targetMarkArea: Boolean(option.series[0].markArea),
    }
  })
  const expectState = async expected => expect.poll(readWeather).toEqual(expected)

  // 默认选中目标污染物 NO 所在的 NO/NO2 组：两条本站曲线（与小时时序图合并图一致）；
  // NO 的剔除区间随组显示；轴收紧到 08:00~10:00 观测范围
  await expect(switchGroup.getByRole('button', { name: 'NO/NO2', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expectState({
    seriesNames: ['NO（本站）', 'NO2（本站）', '风速 (m/s)', '风向', '温度 (°C)', '湿度 (%)', '大气压 (hPa)'],
    seriesAxis: [0, 0, 1, 2, 3, 3, 4],
    axisNames: ['μg/m³', '风速 (m/s)', '', '温度/湿度', '气压 (hPa)'],
    axisRange: { min: Date.parse('2026-10-23T08:00:00'), max: Date.parse('2026-10-23T10:00:00') },
    pollutantSlotCount: 3,
    targetMarkArea: true,
  })

  // 切到 O3：本站 O3 + 互证 NO2（单向配对）；NO/NO2 组的剔除区间不随图
  await switchGroup.getByRole('button', { name: 'O3', exact: true }).click()
  await expect(switchGroup.getByRole('button', { name: 'O3', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expectState({
    seriesNames: ['O3（本站）', 'NO2（同站互证）', '风速 (m/s)', '风向', '温度 (°C)', '湿度 (%)', '大气压 (hPa)'],
    seriesAxis: [0, 0, 1, 2, 3, 3, 4],
    axisNames: ['μg/m³', '风速 (m/s)', '', '温度/湿度', '气压 (hPa)'],
    axisRange: { min: Date.parse('2026-10-23T08:00:00'), max: Date.parse('2026-10-23T10:00:00') },
    pollutantSlotCount: 3,
    targetMarkArea: false,
  })

  // 切到 CO：无配对单曲线，mg/m³ 序列挂右侧次轴（各 grid 的 yAxis 连续分组：紧跟主轴）
  await switchGroup.getByRole('button', { name: 'CO', exact: true }).click()
  await expectState({
    seriesNames: ['CO（本站）', '风速 (m/s)', '风向', '温度 (°C)', '湿度 (%)', '大气压 (hPa)'],
    seriesAxis: [1, 2, 3, 4, 4, 5],
    axisNames: ['μg/m³', 'mg/m³', '风速 (m/s)', '', '温度/湿度', '气压 (hPa)'],
    axisRange: { min: Date.parse('2026-10-23T08:00:00'), max: Date.parse('2026-10-23T10:00:00') },
    pollutantSlotCount: 3,
    targetMarkArea: false,
  })

  // 小时时序图不受切换影响：仍按拆图逻辑渲染
  await expect(page.locator('#wor-section-station_hour canvas').first()).toBeVisible()
  expect(errors).toEqual([])
})
