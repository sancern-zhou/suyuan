import { createRequire } from 'node:module'
import { resolve } from 'node:path'

const require = createRequire(import.meta.url)
const echarts = require(resolve(process.argv[2], 'node_modules/echarts'))
const input = await new Promise((resolveInput, reject) => {
  let data = ''
  process.stdin.setEncoding('utf8')
  process.stdin.on('data', chunk => { data += chunk })
  process.stdin.on('end', () => resolveInput(JSON.parse(data)))
  process.stdin.on('error', reject)
})
const { option, width, height } = input
const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width, height })
try {
  chart.setOption({ ...option, backgroundColor: option.backgroundColor || '#fff', animation: false })
  process.stdout.write(chart.renderToSVGString())
} finally {
  chart.dispose()
}
