// Package the SAME built chart component for Android; no second frontend source/bundle.
import { readFile, mkdir, copyFile, writeFile, rm } from 'node:fs/promises'
import { resolve, dirname } from 'node:path'
const [source, destination] = process.argv.slice(2)
if (!source || !destination) throw new Error('Usage: packageChartRenderer.mjs <frontend/dist> <generated assets/charts>')
const manifest = JSON.parse(await readFile(resolve(source, '.vite/manifest.json'), 'utf8'))
if (!manifest['chart.html']) throw new Error('Run npm run build:standalone in frontend first')
const files = new Set(), visited = new Set()
function collect(key) {
  if (visited.has(key)) return
  visited.add(key)
  const chunk = manifest[key]
  if (!chunk) throw new Error(`Missing chart dependency: ${key}`)
  for (const file of [chunk.file, ...(chunk.css || []), ...(chunk.assets || [])]) files.add(file)
  for (const dependency of [...(chunk.imports || []), ...(chunk.dynamicImports || [])]) collect(dependency)
}
collect('chart.html')
await rm(destination, { recursive: true, force: true })
await mkdir(destination, { recursive: true })
for (const file of files) {
  const target = resolve(destination, file)
  await mkdir(dirname(target), { recursive: true })
  await copyFile(resolve(source, file), target)
}
const html = (await readFile(resolve(source, 'chart.html'), 'utf8')).replace(/(src|href)="[^"]*\/assets\//g, '$1="/assets/')
await writeFile(resolve(destination, 'chart.html'), html)
console.log(`Packaged shared chart renderer (${files.size} assets)`)
