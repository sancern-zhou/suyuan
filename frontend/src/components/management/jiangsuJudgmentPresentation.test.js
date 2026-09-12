import assert from 'node:assert/strict'
import test from 'node:test'
import { jiangsuJudgmentDetails, jiangsuReviewStatus } from './jiangsuJudgmentPresentation.js'

test('impact analysis keeps all four dimensions including historical missing data', () => {
  const rows = jiangsuJudgmentDetails({ data_impact: '有数据影响', data_analysis: { station_series_analysis: '实测连续断数' } })
  assert.equal(rows.find(row => row.key === 'station_series_analysis').value, '实测连续断数')
  assert.match(rows.find(row => row.key === 'regional_comparison_analysis').value, /未提交/)
  assert.equal(rows.length, 5)
  assert.deepEqual(jiangsuJudgmentDetails(null), [])
  assert.equal(jiangsuJudgmentDetails({ data_impact: '无数据影响' }).length, 1)
})

test('P3 waits for archive without changing the persisted human-review state', () => {
  const review = { category: '智能事件', status: 'pending_review', sections: [{ fields: [{ key: 'suggested_level', value: 'P3' }] }] }
  assert.equal(jiangsuReviewStatus(review), '待归档')
  assert.equal(review.status, 'pending_review')
  assert.equal(jiangsuReviewStatus({ ...review, sections: [] }), '待复核')
  assert.equal(jiangsuReviewStatus({ ...review, category: '其他' }), null)
})
