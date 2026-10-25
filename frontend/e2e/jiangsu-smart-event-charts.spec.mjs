import { expect, test } from 'playwright/test'

const event = {
  event_id: 'chart-event', event_name: '图表回归事件', site_name: '测试站点',
  evidence_package: { sources: {
    monitoring: { status: 'success', data: { station_hour: { data: [{ timePoint: '2026-09-10 08:00:00', pM10: 999 }] }, station_5minute: { data: [
      { timePoint: '2026-09-10 08:00:00', pM10: 30, pM2_5: 15, sO2: 4, nO2: 12, co: 0.5, o3: 40 },
      { timePoint: '2026-09-10 08:05:00', pM10: 35, pM2_5: 18, sO2: 5, nO2: 14, co: 0.6, o3: 45 },
    ] } } },
    comparison: { regional_deltas: { nearby_station_delta: { PM10: 5 }, same_city_delta: { PM10: 3 } } },
  } },
}

test('evidence charts render after opening detail and remounting their containers', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname
    const payload = pathname.endsWith('/tasks') ? { tasks: [] }
      : pathname.endsWith('/config') ? { config: {} }
        : pathname.endsWith('/chart-event') ? { event }
          : { events: [event] }
    return route.fulfill({ json: payload })
  })
  await page.route('**/__jiangsu_chart_test__', route => route.fulfill({
    contentType: 'text/html',
    body: `<div id="app" style="height:900px"></div><script type="module">
      import { createApp, h, reactive } from '/node_modules/.vite/deps/vue.js'
      import Panel from '/src/components/management/SmartEventCenterPanel.vue'
      window.panelProps = reactive({ workspaceCommand: null })
      window.panelApp = createApp({ render: () => h(Panel, window.panelProps) })
      window.panelApp.mount('#app')
    </script>`,
  }))
  await page.goto('/__jiangsu_chart_test__')
  await page.getByRole('button', { name: '查看详情', exact: true }).click()

  // 10-24 起监测源不在详情页单独成区（小时数据统一走片区对比呈现），图表只剩区域差异柱状图
  const readCharts = () => page.evaluate(async () => {
    const echarts = await import('/node_modules/.vite/deps/echarts.js')
    return [...document.querySelectorAll('.workbench-section .chart-canvas')].map(holder => {
      const chart = echarts.getInstanceByDom(holder)
      return chart ? { width: chart.getWidth(), times: chart.getOption().xAxis[0].data, series: chart.getOption().series.map(item => item.data) } : null
    })
  })
  const expectCharts = async () => {
    await expect.poll(readCharts).toEqual([
      { width: expect.any(Number), times: ['PM10'], series: [[5], [3]] },
    ])
    expect((await readCharts()).every(chart => chart.width > 0)).toBe(true)
  }
  await expectCharts()

  await page.getByRole('button', { name: '返回列表', exact: true }).click()
  await page.getByRole('button', { name: '查看详情', exact: true }).click()
  await expectCharts()
  await page.evaluate(() => { window.panelProps.workspaceCommand = { type: 'show_operation_history', event_id: 'chart-event' } })
  await expect(page.getByRole('region', { name: '事件操作历史', exact: true })).toBeVisible()
  await page.evaluate(() => { window.panelProps.workspaceCommand = { type: 'open_event_detail', event_id: 'chart-event' } })
  await expectCharts()
  await page.evaluate(() => window.panelApp.unmount())
  expect(errors).toEqual([])
})


test('event list requests ten summaries and pages without waiting for background sync', async ({ page }) => {
  const requests = []
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    requests.push(url)
    if (url.searchParams.get('refresh') === 'true') {
      await route.fulfill({ json: { source_metadata: { sync: { in_progress: true } } } })
      return
    }
    const current = Number(url.searchParams.get('page') || 1)
    const events = Array.from({ length: current === 3 ? 3 : 10 }, (_, index) => ({
      event_id: `${(current - 1) * 10 + index}`, event_name: `分页事件${(current - 1) * 10 + index}`,
    }))
    await route.fulfill({ json: { events, page: current, total: 23,
      stats: { total: 23, pending: 23, stations: 1 }, filters: { statuses: [], types: [] } } })
  })
  await page.route('**/__jiangsu_page_test__', route => route.fulfill({
    contentType: 'text/html',
    body: `<div id="app"></div><script type="module">
      import { createApp } from '/node_modules/.vite/deps/vue.js'
      import Panel from '/src/components/management/SmartEventCenterPanel.vue'
      createApp(Panel).mount('#app')
    </script>`,
  }))
  await page.goto('/__jiangsu_page_test__')
  await expect(page.locator('.event-table tbody tr')).toHaveCount(10)
  await expect(page.getByText('分页事件0', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.getByText('分页事件10', { exact: true })).toBeVisible()
  await expect(page.getByText('第 2 / 3 页')).toBeVisible()
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.locator('.event-table tbody tr')).toHaveCount(3)
  await expect(page.getByRole('button', { name: '下一页' })).toBeDisabled()
  expect(requests.filter(url => url.pathname.endsWith('/smart-events')).every(url => url.searchParams.get('limit') === '10')).toBe(true)
})

test('event detail appears while its task request is still pending', async ({ page }) => {
  let releaseTasks
  const tasksReady = new Promise(resolve => { releaseTasks = resolve })
  await page.route('**/api/**', async route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname.endsWith('/tasks')) {
      await tasksReady
      await route.fulfill({ json: { tasks: [] } })
      return
    }
    await route.fulfill({ json: pathname.endsWith('/chart-event') ? { event } : { events: [event] } })
  })
  await page.route('**/__jiangsu_detail_test__', route => route.fulfill({
    contentType: 'text/html',
    body: `<div id="app" style="height:900px"></div><script type="module">
      import { createApp } from '/node_modules/.vite/deps/vue.js'
      import Panel from '/src/components/management/SmartEventCenterPanel.vue'
      createApp(Panel).mount('#app')
    </script>`,
  }))
  try {
    await page.goto('/__jiangsu_detail_test__')
    await page.getByRole('button', { name: '查看详情', exact: true }).click()
    await expect(page.locator('.delta-canvas canvas')).toBeVisible()
    await expect(page.getByText('正在加载详情...', { exact: true })).toHaveCount(0)
  } finally {
    releaseTasks()
  }
})

test('weather chart switches pollutant groups with same-station verification curve', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const event = {
    event_id: 'weather-event', event_name: '气象切换事件', site_name: '测试站点',
    evidence_package: { collection_policy: { instrument_target_pollutants: ['PM2.5'] }, sources: {
      monitoring: { status: 'success', data: { station_hour: { data: [
        { timePoint: '2026-09-10 08:00:00', pM10: 90, pM2_5: 60, nO2: 20, co: 0.9, o3: 80 },
        { timePoint: '2026-09-10 09:00:00', pM10: 95, pM2_5: 63, nO2: 22, co: 0.8, o3: 84 },
      ] } } },
      weather: { status: 'success', data: [
        { timePoint: '2026-09-10 08:00:00', windSpeed: 2.1, windDirection: 120, temperature: 24, humidity: 60, pressure: 1006 },
        { timePoint: '2026-09-10 09:00:00', windSpeed: 2.4, windDirection: 135, temperature: 25, humidity: 58, pressure: 1007 },
      ] },
    } } }
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname
    const payload = pathname.endsWith('/tasks') ? { tasks: [] }
      : pathname.endsWith('/config') ? { config: {} }
        : pathname.endsWith('/weather-event') ? { event }
          : { events: [event] }
    return route.fulfill({ json: payload })
  })
  await page.route('**/__jiangsu_weather_switch_test__', route => route.fulfill({
    contentType: 'text/html',
    body: `<div id="app" style="height:900px"></div><script type="module">
      import { createApp, h, reactive } from '/node_modules/.vite/deps/vue.js'
      import Panel from '/src/components/management/SmartEventCenterPanel.vue'
      window.panelProps = reactive({ workspaceCommand: null })
      window.panelApp = createApp({ render: () => h(Panel, window.panelProps) })
      window.panelApp.mount('#app')
    </script>`,
  }))
  await page.goto('/__jiangsu_weather_switch_test__')
  await page.getByRole('button', { name: '查看详情', exact: true }).click()

  const readWeather = () => page.evaluate(async () => {
    const echarts = await import('/node_modules/.vite/deps/echarts.js')
    const holder = document.querySelector('.weather-chart-canvas')
    const chart = holder && echarts.getInstanceByDom(holder)
    if (!chart) return null
    const option = chart.getOption()
    return {
      seriesNames: option.series.map(item => item.name),
      yAxisNames: option.yAxis.map(axis => axis.name || ''),
      coAxisIndex: option.series.find(item => item.name === 'CO（本站）')?.yAxisIndex,
    }
  })
  const expectWeather = async expected => expect.poll(readWeather).toEqual(expected)

  const switchGroup = page.getByRole('group', { name: '气象图污染物切换' })
  // 有数据的污染物：PM10/PM2.5 双向配对并组，NO2/CO/O3 独立（SO2 无数据不出现）
  await expect(switchGroup.getByRole('button')).toHaveCount(4)
  // 默认选中事件目标污染物 PM2.5 所在组，无 CO 时不渲染 mg/m³ 次轴
  await expect(switchGroup.getByRole('button', { name: 'PM10/PM2.5', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expectWeather({
    seriesNames: ['PM10（本站）', 'PM2.5（本站）', '气温(℃)', '湿度(%)', '风速(m/s)', '气压(hPa)', '风向'],
    yAxisNames: ['浓度 (μg/m³)', '风速 (m/s)', '', '气温 (℃) / 湿度 (%)', '气压 (hPa)'],
    coAxisIndex: undefined,
  })

  // 切到 O3：本站 O3 + NO2 同站互证（单向配对）
  await switchGroup.getByRole('button', { name: 'O3', exact: true }).click()
  await expectWeather({
    seriesNames: ['O3（本站）', 'NO2（同站互证）', '气温(℃)', '湿度(%)', '风速(m/s)', '气压(hPa)', '风向'],
    yAxisNames: ['浓度 (μg/m³)', '风速 (m/s)', '', '气温 (℃) / 湿度 (%)', '气压 (hPa)'],
    coAxisIndex: undefined,
  })

  // 切到 CO：mg/m³ 次轴动态出现，后续气象轴索引顺移
  await switchGroup.getByRole('button', { name: 'CO', exact: true }).click()
  await expectWeather({
    seriesNames: ['CO（本站）', '气温(℃)', '湿度(%)', '风速(m/s)', '气压(hPa)', '风向'],
    yAxisNames: ['浓度 (μg/m³)', 'CO (mg/m³)', '风速 (m/s)', '', '气温 (℃) / 湿度 (%)', '气压 (hPa)'],
    coAxisIndex: 1,
  })
  expect(errors).toEqual([])
})
