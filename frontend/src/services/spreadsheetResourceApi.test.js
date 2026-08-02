import assert from 'node:assert/strict'
import test from 'node:test'

import { coerceSpreadsheetCell, saveSpreadsheetResource } from './spreadsheetResourceApi.js'

test('saves workbook bytes through the resource scoped multipart action', async () => {
  const calls = []
  const fetchImpl = async (url, options) => {
    calls.push({ url, options })
    return {
      ok: true,
      json: async () => ({ success: true, resource_version: 4 })
    }
  }
  const receipt = await saveSpreadsheetResource(
    { label: '数据.xlsx', actions: { save: '/api/sessions/s1/resources/r1/save' } },
    new Uint8Array([80, 75, 3, 4]),
    fetchImpl
  )

  assert.equal(calls[0].url, '/api/sessions/s1/resources/r1/save')
  assert.equal(calls[0].options.method, 'POST')
  assert.ok(calls[0].options.body instanceof FormData)
  assert.equal(calls[0].options.body.get('file').name, '数据.xlsx')
  assert.equal(receipt.resource_version, 4)
})

test('rejects spreadsheet save when the unified action is unavailable', async () => {
  await assert.rejects(
    () => saveSpreadsheetResource({ label: '数据.xlsx', actions: {} }, new Uint8Array()),
    /不支持保存/
  )
})

test('cell edits preserve style and numeric value types', () => {
  const cell = coerceSpreadsheetCell({ t: 'n', v: 1, w: '1.00', s: { numFmt: '0.00' } }, '2.5')
  assert.equal(cell.t, 'n')
  assert.equal(cell.v, 2.5)
  assert.deepEqual(cell.s, { numFmt: '0.00' })
  assert.equal('w' in cell, false)
})

test('formula edits remain formulas while text cells keep numeric-looking text', () => {
  const formula = coerceSpreadsheetCell({ t: 'n', v: 3, s: { fill: 'blue' } }, '=SUM(A1:A2)')
  assert.equal(formula.t, 'n')
  assert.equal(formula.f, 'SUM(A1:A2)')
  assert.deepEqual(formula.s, { fill: 'blue' })

  const text = coerceSpreadsheetCell({ t: 's', v: '001' }, '002')
  assert.deepEqual(text, { t: 's', v: '002' })
})
