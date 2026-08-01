import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const forbidden = [
  'officeDocumentHistory', 'lastOfficeDocument', 'visualizationHistory',
  'extractOfficeDocumentsFromMessages', 'getSessionOfficeDocuments',
  'getSessionVisualizations', 'getSessionDrawioBoard',
  '/office-documents', '/visualizations', '/api/file/',
  '/api/office/download-word', '/api/office/download-ppt', '/api/office/download-excel',
  'pdf_preview', 'html_preview', 'markdown_preview', 'spreadsheet_preview', 'ppt_preview'
]

async function productionFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = await Promise.all(entries.map(async entry => {
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) return productionFiles(target)
    if (!/\.(js|mjs|vue)$/.test(entry.name) || /\.test\.(js|mjs)$/.test(entry.name)) return []
    return [target]
  }))
  return files.flat()
}

test('frontend production source contains no legacy resource mechanism', async () => {
  const violations = []
  for (const file of await productionFiles(sourceRoot)) {
    const source = await readFile(file, 'utf8')
    for (const token of forbidden) {
      if (source.includes(token)) violations.push(`${path.relative(sourceRoot, file)}: ${token}`)
    }
  }
  assert.deepEqual(violations, [])
})
