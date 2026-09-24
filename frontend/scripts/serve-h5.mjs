#!/usr/bin/env node
/**
 * 零依赖的静态服务器：把 `.preview-h5` 目录当网站发出去（默认 8100 端口）。
 *
 * 为什么单独写一个：`python -m http.server` 也能干这事，但那样又多依赖一个 Python；
 * 这个脚本只用 Node 自带模块，和 Taro 的依赖环境完全一致。
 *
 * 用法：
 *   pnpm preview:h5:serve
 *   pnpm preview:h5:serve --port 8200
 */

import { createReadStream, existsSync, statSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, extname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const rootDir = resolve(frontendRoot, '.preview-h5')

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.mp3': 'audio/mpeg',
  '.txt': 'text/plain; charset=utf-8'
}

function parsePort(argv) {
  const index = argv.indexOf('--port')
  const raw = index >= 0 ? argv[index + 1] : undefined
  const port = Number(raw ?? 8100)
  return Number.isInteger(port) && port > 0 && port < 65536 ? port : 8100
}

function send(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8' })
  res.end(body)
}

const port = parsePort(process.argv.slice(2))

if (!existsSync(join(rootDir, 'index.html'))) {
  console.error(`✖ 预览目录里没有 index.html：${rootDir}`)
  console.error('  请先执行：pnpm preview:h5')
  process.exit(1)
}

const server = createServer((req, res) => {
  const urlPath = decodeURIComponent((req.url ?? '/').split('?')[0])
  let filePath = resolve(join(rootDir, urlPath))

  // 防目录穿越：解析后的路径必须仍在预览目录内
  if (filePath !== rootDir && !filePath.startsWith(rootDir + sep)) {
    return send(res, 403, 'Forbidden')
  }

  if (existsSync(filePath) && statSync(filePath).isDirectory()) {
    filePath = join(filePath, 'index.html')
  }
  // 前端路由（无扩展名的路径）回落到 index.html
  if (!existsSync(filePath) && !extname(filePath)) {
    filePath = join(rootDir, 'index.html')
  }
  if (!existsSync(filePath)) {
    return send(res, 404, `404 Not Found: ${urlPath}`)
  }

  res.writeHead(200, {
    'Content-Type': MIME_TYPES[extname(filePath).toLowerCase()] ?? 'application/octet-stream',
    'Cache-Control': 'no-store'
  })
  createReadStream(filePath).pipe(res)
})

server.listen(port, '127.0.0.1', () => {
  console.log(`H5 预览已启动：http://127.0.0.1:${port}`)
  console.log(`  目录：${rootDir}`)
  console.log('  停止：Ctrl+C')
})
