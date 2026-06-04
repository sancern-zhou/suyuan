import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const viewPath = resolve('src/views/DemoShowcase.vue')
const routerPath = resolve('src/router/index.js')

const viewSource = readFileSync(viewPath, 'utf8')
const routerSource = readFileSync(routerPath, 'utf8')

assert.match(viewSource, /办公室的专业工作站，口袋里的随身助理/)
assert.match(viewSource, /Web端 · 专业工作站/)
assert.match(viewSource, /移动端 · 随身助理/)
assert.match(viewSource, /同样的 AI 能力/)
assert.match(routerSource, /DemoShowcase/)
assert.match(routerSource, /\/demo-showcase/)

console.log('DemoShowcase static checks passed')
