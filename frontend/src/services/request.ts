import Taro from '@tarojs/taro'

import { storage } from './storage'

/**
 * 统一请求层：
 * - 自动注入 Authorization
 * - 自动解包 {code, message, data}
 * - 网络错误 / 5xx / 超时自动重试（默认 2 次），4xx 不重试
 * - 401 清掉本地 token，让页面重新静默登录
 */
const BASE_URL = process.env.TARO_APP_API_BASE || 'http://127.0.0.1:8000'
const DEFAULT_TIMEOUT = 12000
const DEFAULT_RETRY = 2

interface Envelope<T> {
  code: string
  message: string
  data: T
}

export class ApiError extends Error {
  code: string
  status: number

  constructor(code: string, message: string, status = 0) {
    super(message)
    this.code = code
    this.status = status
  }
}

/**
 * 401 自愈：token 失效（例如后端换了密钥、用户被清号）时，自动重新静默登录一次并重试原请求。
 * 由 UserProvider 在挂载时注册，避免请求层直接依赖登录逻辑造成循环引用。
 */
let unauthorizedHandler: (() => Promise<boolean>) | null = null

export function setUnauthorizedHandler(handler: () => Promise<boolean>): void {
  unauthorizedHandler = handler
}

export interface RequestOptions {
  url: string
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: Record<string, unknown>
  timeout?: number
  retry?: number
  auth?: boolean
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function send<T>(options: RequestOptions, attempt: number): Promise<T> {
  const retry = options.retry ?? DEFAULT_RETRY
  const header: Record<string, string> = { 'Content-Type': 'application/json' }
  if (options.auth !== false) {
    const token = storage.getToken()
    if (token) header.Authorization = `Bearer ${token}`
  }

  try {
    const response = await Taro.request({
      url: `${BASE_URL}${options.url}`,
      method: options.method ?? 'GET',
      data: options.data,
      header,
      timeout: options.timeout ?? DEFAULT_TIMEOUT
    })

    const status = response.statusCode
    const body = response.data as Envelope<T>

    if (status >= 200 && status < 300 && body && body.code === 'OK') {
      return body.data
    }

    if (status >= 500 && attempt < retry) {
      await sleep(300 * (attempt + 1))
      return send<T>(options, attempt + 1)
    }

    if (status === 401) {
      storage.clearToken()
      if (attempt === 0 && unauthorizedHandler) {
        const recovered = await unauthorizedHandler()
        if (recovered) return send<T>(options, attempt + 1)
      }
    }
    throw new ApiError(
      body?.code || `HTTP_${status}`,
      body?.message || '服务开小差了，稍后再试试',
      status
    )
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (attempt < retry) {
      await sleep(300 * (attempt + 1))
      return send<T>(options, attempt + 1)
    }
    throw new ApiError('NETWORK_ERROR', '网络打了个盹，点一下重试')
  }
}

export function request<T>(options: RequestOptions): Promise<T> {
  return send<T>(options, 0)
}
