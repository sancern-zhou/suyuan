import { expect, test } from 'playwright/test'

const CODE = 'FA-FIVE-MINUTE'
const points = [
  { time: '2026-11-06 00:00:00', value: 900 },
  { time: '2026-11-07 08:10:00', value: 401, flag: 'PS' },
  { time: '2026-11-07 08:15:00', value: 458, flag: 'PS' },
  { time: '2026-11-07 08:20:00', value: 2 },
  { time: '2026-11-07 10:45:00', value: 428, flag: 'PZ' },
  { time: '2026-11-07 11:05:00', value: 2 },
  { time: '2026-11-07 17:35:00', value: 3 },
]
const entry = {
  working_order_code: CODE, title: 'NO跨度检查工单', site_name: '分钟证据站', pollutant: 'NO',
  window_start: '2026-11-06 00:00:00', window_end: '2026-11-07 23:59:59', status: '待归档',
}
const source = {
  source: 'station_5minute',
  data: {
    available_pollutants: ['NO', 'NO2', 'CO'],
    units: { NO: 'μg/m³', NO2: 'μg/m³', CO: 'mg/m³' },
    coverage: {
      query_start: entry.window_start, query_end: entry.window_end,
      actual_start: '2026-11-06 00:00:00', actual_end: '2026-11-07 17:35:00',
      saved_record_count: 500, platform_record_count: 576, missing_record_count: 76,
      fault_time: '2026-11-07 10:41:30', default_anchor: { time: '2026-11-07 11:03:40' },
      default_window: ['2026-11-07 07:49:56', '2026-11-07 13:03:40'],
      data_type_label: '原始实况（工况）',
      warning: '尾部 76 条未入包；实际覆盖截至 2026-11-07 17:35。',
    },
    points_by_pollutant: {
      NO: points,
      NO2: points.map(point => ({ ...point, value: point.flag ? -2 : 10 })),
      CO: points.map(point => ({ time: point.time, value: 0.645 })),
    },
    rows: points.map(point => ({
      timePoint: point.time, no: `${point.value}${point.flag ? `(${point.flag})` : ''}`,
      nO2: point.flag ? `-2(${point.flag})` : '10', co: '0.645',
    })),
  },
}

async function openWorkbench(page, minute = source) {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const sources = {
    work_order: { status: 'success', record_count: 1 },
    station_hour: { status: 'success', record_count: 2 },
    ...(minute ? { station_5minute: { status: 'partial', record_count: 500 } } : {}),
    band: { status: 'empty', record_count: 0 },
  }
  await page.route('**/api/**', route => {
    const { pathname } = new URL(route.request().url())
    if (pathname.endsWith(`/work-order-reviews/${CODE}`)) {
      return route.fulfill({ json: { entry, index: { sources, mark_areas: [], operations: [] } } })
    }
    const match = /\/sources\/(\w+)$/.exec(pathname)
    if (match) {
      if (match[1] === 'station_5minute') return route.fulfill({ json: minute })
      if (match[1] === 'station_hour') return route.fulfill({ json: { source: 'station_hour', data: {
        pollutant: 'NO', unit: 'μg/m³', comparison_pollutant: 'NO2',
        points: [{ time: '2026-11-07 08:00:00', value: 2 }, { time: '2026-11-07 09:00:00', value: 3 }],
        comparison_points: [{ time: '2026-11-07 08:00:00', value: 10 }],
      } } })
      return route.fulfill({ json: { source: match[1], data: null } })
    }
    return route.fulfill({ json: { orders: [entry], total: 1, statuses: ['待归档'] } })
  })
  await page.route('**/__wor_five_minute_test__', route => route.fulfill({
    contentType: 'text/html',
    body: `<meta charset="utf-8"><div id="app" style="height:900px"></div><script type="module">
      import { createApp, h } from '/node_modules/.vite/deps/vue.js'
      import Panel from '/src/components/management/WorkOrderReviewCenterPanel.vue'
      import '/src/styles/tokens.css'
      createApp({ render: () => h(Panel, { workspaceCommand: { type:'open_work_order_review', working_order_code:'${CODE}' }, showListActions:false }) }).mount('#app')
    </script>`,
  }))
  await page.goto('/__wor_five_minute_test__')
  await expect(page.getByRole('button', { name: '4. 5分钟原始监测', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '4. 5分钟原始监测', exact: true }).click()
  return errors
}

async function readChart(page) {
  return page.locator('#wor-section-station_5minute .chart-surface').evaluate(async holder => {
    const echarts = await import('/node_modules/.vite/deps/echarts_core.js')
    const chart = echarts.getInstanceByDom(holder)
    const option = chart.getOption()
    const time = Date.parse('2026-11-07T08:10:00')
    const series = option.series.map(item => ({
      name: item.name, type: item.type, unit: option.yAxis[0].name, color: item.itemStyle?.color,
      values: (item.data || []).filter(point => point.value?.[1] !== null),
    }))
    const first = option.series[0]
    const point = first.data.find(item => item.value?.[0] === time)
    const tooltip = option.tooltip[0].formatter([{ value: point?.value, data: point, seriesName: first.name, marker: '', seriesType:'line' }])
    return { series, min:option.xAxis[0].min, max:option.xAxis[0].max, tooltip }
  })
}

test('minute card shows real coverage, QC diamonds, raw flags and window controls', async ({ page }) => {
  const errors = await openWorkbench(page)
  const card = page.locator('#wor-section-station_5minute')
  await expect(card.getByText('实际入包 500/576 条', { exact: true })).toBeVisible()
  await expect(card.getByRole('alert')).toContainText('76 条未入包')
  await expect(card.locator('canvas')).toBeVisible()
  const initial = await readChart(page)
  expect(initial.series.filter(item => item.type === 'scatter')).toHaveLength(2)
  expect(initial.tooltip).toContain('401')
  expect(initial.tooltip).toContain('PS（跨度检查）')
  expect(initial.tooltip).toContain('原始实况（工况）')
  expect(initial.min).toBe(Date.parse('2026-11-07T07:49:56'))
  expect(initial.series[0].values.some(point => point.value[1] === 900)).toBe(false)
  await card.getByRole('button', { name:'完整取证窗口', exact:true }).click()
  expect((await readChart(page)).max).toBe(Date.parse('2026-11-07T23:59:59'))
  await card.getByRole('button', { name:'处置与质控窗口', exact:true }).click()
  await card.getByRole('button', { name:'展开原始数据表', exact:true }).click()
  await expect(card.getByRole('cell', { name:'401(PS)', exact:true })).toBeVisible()
  await expect(card.getByRole('cell', { name:'428(PZ)', exact:true })).toBeVisible()
  await card.getByRole('checkbox', { name:'仅看质控标识' }).check()
  await expect(card.getByRole('row')).toHaveCount(4)
  await card.getByRole('checkbox', { name:'仅看质控标识' }).uncheck()
  await card.getByRole('button', { name:'CO', exact:true }).click()
  expect((await readChart(page)).series[0].unit).toBe('mg/m³')
  await card.getByRole('checkbox', { name:'仅看质控标识' }).check()
  await expect(card.getByText('当前污染物未记录质控标识，可取消筛选查看全部原始值。')).toBeVisible()
  await card.getByRole('checkbox', { name:'仅看质控标识' }).uncheck()
  await expect(card.locator('canvas')).toBeVisible()
  await card.getByRole('button', { name:'查看对应小时曲线', exact:true }).click()
  await expect(page.getByRole('button', { name:'3. 污染物小时时序', exact:true })).toHaveClass(/active/)
  expect(errors).toEqual([])
})

test('failed collections keep their warning visible even with no plottable observations', async ({ page }) => {
  const minute = { source:'station_5minute', data: {
    points_by_pollutant: {}, rows: [], available_pollutants: [],
    coverage: { query_start:entry.window_start, query_end:entry.window_end,
      saved_record_count:0, platform_record_count:0, failed_chunk_count:2,
      warning:'2 个5分钟数据分片查询失败，当前曲线不覆盖完整取证窗口。' },
  } }
  const errors = await openWorkbench(page, minute)
  const card = page.locator('#wor-section-station_5minute')
  await expect(card.getByRole('alert')).toContainText('2 个5分钟数据分片查询失败')
  await expect(card.getByText('已保存的原始记录无可绘制数值；可展开原始数据表核对缺失值和标识。')).toBeVisible()
  expect(errors).toEqual([])
})

test('raw missing observations and their flags remain viewable without numeric curves', async ({ page }) => {
  const minute = { source:'station_5minute', data: {
    points_by_pollutant:{}, available_pollutants:['NO'],
    coverage: { ...source.data.coverage, actual_start:'2026-11-07 08:10:00', actual_end:'2026-11-07 08:15:00' },
    rows:[{ timePoint:'2026-11-07 08:10:00', NO:'--(PS)' }, { timePoint:'2026-11-07 08:15:00', NO:'-999（PZ）' }],
  } }
  const errors = await openWorkbench(page, minute)
  const card = page.locator('#wor-section-station_5minute')
  await card.getByRole('button', { name:'展开原始数据表', exact:true }).click()
  await expect(card.getByRole('cell', { name:'--(PS)', exact:true })).toBeVisible()
  await expect(card.getByRole('cell', { name:'-999（PZ）', exact:true })).toBeVisible()
  await card.getByRole('checkbox', { name:'仅看质控标识' }).check()
  await expect(card.getByRole('row')).toHaveCount(3)
  expect(errors).toEqual([])
})

test('old packages expose an explicit empty minute card without requesting a nonexistent source', async ({ page }) => {
  const requested = []
  page.on('request', request => { if (request.url().includes('/sources/station_5minute')) requested.push(request.url()) })
  const errors = await openWorkbench(page, null)
  await expect(page.getByText('历史审核包未保存5分钟证据源')).toBeVisible()
  await expect(page.getByText('该审核包暂无可展示的5分钟原始监测数据。')).toBeVisible()
  expect(requested).toEqual([])
  expect(errors).toEqual([])
})
