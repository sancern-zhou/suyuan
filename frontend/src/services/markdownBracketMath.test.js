import assert from 'node:assert/strict'
import test from 'node:test'
import MarkdownIt from 'markdown-it'
import markdownItKatex from '@traptitech/markdown-it-katex'
import { wrapBracketMath } from './markdownBracketMath.js'

test('chart placeholders with underscores remain intact and do not turn red', () => {
  const content = '单位为“PM2.5日均浓度(μg/m³) / AQI日均值（空气质量等级）”\n\n' +
    '[[chart:echarts_1790562740726228784_0]]\n\n' +
    '## 二、逐小时同步性\n\n' +
    '[[chart:echarts_1790562701562544472_1]]\n\n' +
    '后续分析完整保留。'
  const processed = wrapBracketMath(content)
  assert.equal(processed, content)
  const html = new MarkdownIt().use(markdownItKatex, { throwOnError: false, errorColor: '#cc0000' }).render(processed)
  assert.match(html, /二、逐小时同步性/)
  assert.match(html, /后续分析完整保留/)
  assert.doesNotMatch(html, /katex-error|color:\s*#cc0000/)
})

test('standalone bracketed formulas still convert while links remain intact', () => {
  assert.equal(wrapBracketMath('[x_i]'), '$$x_i$$')
  assert.equal(wrapBracketMath('[AQI_daily](https://example.com)'), '[AQI_daily](https://example.com)')
  assert.equal(wrapBracketMath('[[chart:echarts_1_0]] [x_i]'), '[[chart:echarts_1_0]] $$x_i$$')
})
