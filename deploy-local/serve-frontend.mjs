// 本地前端静态服务 + 反向代理（替代 Linux 部署中的 nginx 容器）
// 路由规则与 frontend/vite.config.js 的 server.proxy 保持一致：
//   /suyuan/api/suyuan/ws  -> ws://127.0.0.1:8000/ws          (去掉 /suyuan/api/suyuan)
//   /suyuan/api/suyuan/*   -> http://127.0.0.1:8000/api/*      (/suyuan/api/suyuan -> /api)
//   /suyuan/api/auth/*     -> http://10.10.204.80:8025/*       (透传)
//   /suyuan/*              -> frontend/dist 静态文件, SPA 回退 index.html
// 可用环境变量覆盖: FRONTEND_PORT, BACKEND_TARGET, AUTH_PROXY_TARGET
import http from 'node:http'
import net from 'node:net'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const DIST = path.resolve(__dirname, '..', 'frontend', 'dist')
const PORT = Number(process.env.FRONTEND_PORT || 5176)
const BACKEND = new URL(process.env.BACKEND_TARGET || 'http://127.0.0.1:8000')
const AUTH = new URL(process.env.AUTH_PROXY_TARGET || 'http://10.10.204.80:8025')
const BASE = '/suyuan/'

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2',
  '.ttf': 'font/ttf', '.map': 'application/json', '.txt': 'text/plain', '.wasm': 'application/wasm'
}

function proxy(req, res, target, rewritePath) {
  const headers = { ...req.headers, host: target.host }
  delete headers['proxy-authorization']
  const upstream = http.request(
    { protocol: target.protocol, hostname: target.hostname, port: target.port,
      method: req.method, path: rewritePath(req.url), headers },
    up => { res.writeHead(up.statusCode, up.headers); up.pipe(res) })
  const fail = err => {
    if (res.writableEnded || res.destroyed) return
    if (!res.headersSent) {
      res.writeHead(502, { 'content-type': 'application/json; charset=utf-8' })
      res.end(JSON.stringify({ error: 'backend unreachable', detail: String(err) }))
    } else {
      res.destroy()
    }
  }
  upstream.on('error', fail)
  // 浏览器取消请求时同步释放上游连接，避免残留 socket 拖住后端进程。
  res.on('close', () => {
    if (res.writableEnded) return
    req.unpipe(upstream)
    upstream.destroy()
  })
  req.on('aborted', () => upstream.destroy())
  req.pipe(upstream)
}

function proxyWs(req, socket, head, target, rewritePath) {
  const upstreamPath = rewritePath(req.url)
  const client = net.connect(Number(target.port), target.hostname, () => {
    const lines = [`${req.method} ${upstreamPath} HTTP/1.1`]
    for (const [k, v] of Object.entries(req.headers)) {
      if (k.toLowerCase() === 'host') lines.push(`Host: ${target.host}`)
      else if (!Array.isArray(v)) lines.push(`${k}: ${v}`)
    }
    client.write(lines.join('\r\n') + '\r\n\r\n')
    if (head && head.length) client.write(head)
    socket.pipe(client).pipe(socket)
  })
  client.on('error', () => socket.destroy())
  socket.on('error', () => client.destroy())
}

function serveStatic(req, res) {
  let rel = req.url.slice(BASE.length).split('?')[0]
  rel = decodeURIComponent(rel)
  let file = path.normalize(path.join(DIST, rel))
  if (!file.startsWith(DIST)) { res.writeHead(403).end(); return }
  if (rel === '' || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    file = path.join(DIST, 'index.html') // SPA 回退
  }
  const ext = path.extname(file).toLowerCase()
  const stream = fs.createReadStream(file)
  stream.on('open', () => {
    if (res.destroyed) { stream.destroy(); return }
    res.writeHead(200, { 'content-type': MIME[ext] || 'application/octet-stream' })
  })
  stream.on('error', () => {
    if (!res.headersSent) res.writeHead(404)
    res.end()
  })
  // 客户端中断下载时必须销毁读取流，否则 Windows 会一直锁住该文件，
  // 导致后续 npm run build 在清空 dist 时报 EPERM。
  res.on('close', () => stream.destroy())
  stream.pipe(res)
}

const server = http.createServer((req, res) => {
  const url = req.url
  if (url.startsWith('/suyuan/api/suyuan/ws')) proxy(req, res, BACKEND, u => u.replace(/^\/suyuan\/api\/suyuan/, ''))
  else if (url.startsWith('/suyuan/api/suyuan/')) proxy(req, res, BACKEND, u => u.replace(/^\/suyuan\/api\/suyuan/, '/api'))
  else if (url.startsWith('/suyuan/api/auth/')) proxy(req, res, AUTH, u => u.replace(/^\/suyuan\/api\/auth/, '/api/auth'))
  else if (url.startsWith(BASE)) serveStatic(req, res)
  else if (url === '/' || url === '/suyuan') { res.writeHead(302, { location: BASE }).end() }
  else { res.writeHead(404).end('not found') }
})

server.on('upgrade', (req, socket, head) => {
  if (req.url.startsWith('/suyuan/api/suyuan/ws')) {
    proxyWs(req, socket, head, BACKEND, u => u.replace(/^\/suyuan\/api\/suyuan/, ''))
  } else {
    socket.destroy()
  }
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[suyuan-guangdong] frontend: http://<host>:${PORT}/suyuan/  dist=${DIST}`)
  console.log(`[suyuan-guangdong] api -> ${BACKEND.href}, auth -> ${AUTH.href}`)
})
