import assert from 'node:assert/strict'
import test from 'node:test'

import { applyPreferredChartFont, PREFERRED_CHART_FONT_FAMILY } from './chartTypography.js'

test('chart typography applies the configured font priority to ECharts options', () => {
  const option = applyPreferredChartFont({
    textStyle: { color: '#223344', fontFamily: 'Arial' },
    series: [{ type: 'bar', data: [1] }]
  })

  assert.equal(option.textStyle.fontFamily, PREFERRED_CHART_FONT_FAMILY)
  assert.equal(option.textStyle.color, '#223344')
  assert.match(option.textStyle.fontFamily, /^FZXiaoBiaoSong-B05S, 方正小标宋简体/)
})
