#!/usr/bin/env node
/**
 * 一条命令准备 H5 预览，且不破坏小程序产物。
 *
 * 为什么需要它（背景）：
 *   Taro 的 H5 产物和小程序产物**输出到同一个 `dist` 目录**；而微信开发者工具
 *   按 `project.config.json` 里的 `miniprogramRoot` 去 `dist/` 找 `app.json`。
 *   所以只要单独跑过一次 `build:h5`，`dist` 里的小程序产物就被覆盖，
 *   开发者工具会报「找不到 app.json」。
 *
 * 这个脚本按顺序做三件事：
 *   1. 构建 H5（接口地址默认指向本机后端 http://127.0.0.1:8000）
 *   2. 把 H5 产物同步到 `.preview-h5`（浏览器预览目录）
 *   3. 重新构建小程序产物到 `dist`，把 `app.json` 放回去
 *
 * 小程序那份的接口地址默认**自动探测本机局域网 IP**（不带 --weapp-api-base 时），
 * 因为 `.env.production` 里手写的 IP 会随路由器 DHCP 变化而失效；
 * 探测结果会打印出来，真机连不上时先看这一行。
 *
 * 用法：
 *   pnpm preview:h5                        # 常规用法
 *   pnpm preview:h5 --api-base http://192.168.2.148:8000
 *   pnpm preview:h5 --skip-weapp-restore   # 只做 H5，不恢复小程序产物（会冲掉 dist）
 */

import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, rmSync } from 'node:fs'
import { networkInterfaces } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const distDir = resolve(frontendRoot, 'dist')
const previewDir = resolve(frontendRoot, '.preview-h5')

function detectLanIp() {
  for (const entries of Object.values(networkInterfaces())) {
    for (const entry of entries ?? []) {
      if (entry.family === 'IPv4' && !entry.internal) {
        return entry.address
      }
    }
  }
  return '127.0.0.1'
}

function parseArgs(argv) {
  const options = {
    apiBase: 'http://127.0.0.1:8000',
    weappApiBase: `http://${detectLanIp()}:8000`,
    restoreWeapp: true
  }
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--api-base') {
      options.apiBase = argv[i + 1] ?? options.apiBase
      i += 1
    } else if (arg === '--weapp-api-base') {
      options.weappApiBase = argv[i + 1] ?? options.weappApiBase
      i += 1
    } else if (arg === '--skip-weapp-restore') {
      options.restoreWeapp = false
    } else if (arg === '--help' || arg === '-h') {
      console.log(
        [
          '用法: pnpm preview:h5 [--api-base <url>] [--weapp-api-base <url>] [--skip-weapp-restore]',
          '',
          '  --api-base <url>        H5 产物的后端地址，默认 http://127.0.0.1:8000',
          '  --weapp-api-base <url>  小程序产物的后端地址，默认自动探测本机局域网 IP',
          '  --skip-weapp-restore    跳过「把小程序产物放回 dist」'
        ].join('\n')
      )
      process.exit(0)
    }
  }
  return options
}

function run(label, command, extraEnv = {}) {
  const started = Date.now()
  console.log(`\n▶ ${label}`)
  const result = spawnSync(command, {
    cwd: frontendRoot,
    stdio: 'inherit',
    shell: true,
    env: { ...process.env, ...extraEnv }
  })
  if (result.status !== 0) {
    console.error(`\n✖ ${label} 失败（退出码 ${result.status}）`)
    process.exit(result.status ?? 1)
  }
  console.log(`✔ ${label} 完成（${((Date.now() - started) / 1000).toFixed(1)}s）`)
}

const options = parseArgs(process.argv.slice(2))
console.log('准备 H5 预览：')
console.log(`  前端目录        ${frontendRoot}`)
console.log(`  预览目录        ${previewDir}`)
console.log(`  H5 后端地址     ${options.apiBase}`)
console.log(`  小程序后端地址  ${options.weappApiBase}${options.restoreWeapp ? '' : '（本次不编译小程序）'}`)
console.log(`  恢复小程序产物  ${options.restoreWeapp ? '是（dist 最终是小程序产物）' : '否（dist 最终是 H5 产物）'}`)

// 1) 构建 H5：接口地址在构建期写死，这里统一指向本机后端
run('构建 H5（接口地址写死为上面那个）', 'npm run build:h5', {
  TARO_APP_API_BASE: options.apiBase
})
if (!existsSync(resolve(distDir, 'index.html'))) {
  console.error('\n✖ dist 里没有 index.html，H5 看起来没有构建成功。')
  process.exit(1)
}

// 2) 同步到预览目录（先清空，避免残留上一次的文件）
console.log('\n▶ 同步产物到 .preview-h5')
rmSync(previewDir, { recursive: true, force: true })
cpSync(distDir, previewDir, { recursive: true })
console.log(`✔ 已同步（${previewDir}）`)

// 3) 把小程序产物放回 dist，否则开发者工具会找不到 app.json
if (options.restoreWeapp) {
  run('把小程序产物放回 dist（开发者工具要读 dist/app.json）', 'npm run build:weapp', {
    TARO_APP_API_BASE: options.weappApiBase
  })
  if (!existsSync(resolve(distDir, 'app.json'))) {
    console.error('\n✖ dist 里仍然没有 app.json，小程序产物没构建成功。')
    process.exit(1)
  }
  console.log('✔ dist 已恢复为小程序产物（app.json 就位）')
} else {
  console.log('\n⚠ 已跳过小程序产物恢复：dist 现在是 H5 产物，开发者工具会报找不到 app.json。')
  console.log('  需要时执行：pnpm build:weapp')
}

console.log('\n下一步：')
console.log('  浏览器预览   pnpm preview:h5:serve   然后打开 http://127.0.0.1:8100')
console.log('  小程序预览   在微信开发者工具里点「编译」（导入目录选 frontend/）')
