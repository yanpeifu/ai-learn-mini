import Taro from '@tarojs/taro'

const TOKEN_KEY = 'ai_learn_token'
const DEVICE_KEY = 'ai_learn_device_id'
const PROGRESS_KEY = 'ai_learn_progress'

/** 本地存储：token 与答题进度（切后台/退出后能继续）。 */
export const storage = {
  getToken(): string {
    try {
      return (Taro.getStorageSync(TOKEN_KEY) as string) || ''
    } catch {
      return ''
    }
  },
  setToken(token: string): void {
    try {
      Taro.setStorageSync(TOKEN_KEY, token)
    } catch {
      /* 存储失败不影响主流程 */
    }
  },
  clearToken(): void {
    try {
      Taro.removeStorageSync(TOKEN_KEY)
    } catch {
      /* ignore */
    }
  },
  /** 没有 AppID 时用它生成稳定的 DEV 登录 code，保证同一台设备永远是同一个用户。 */
  getDeviceId(): string {
    try {
      const existing = Taro.getStorageSync(DEVICE_KEY) as string
      if (existing) return existing
      const created = `dev_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`
      Taro.setStorageSync(DEVICE_KEY, created)
      return created
    } catch {
      return 'dev_fallback'
    }
  },
  setProgress(value: unknown): void {
    try {
      Taro.setStorageSync(PROGRESS_KEY, JSON.stringify(value))
    } catch {
      /* ignore */
    }
  },
  getProgress<T>(): T | null {
    try {
      const raw = Taro.getStorageSync(PROGRESS_KEY) as string
      return raw ? (JSON.parse(raw) as T) : null
    } catch {
      return null
    }
  },
  clearProgress(): void {
    try {
      Taro.removeStorageSync(PROGRESS_KEY)
    } catch {
      /* ignore */
    }
  }
}
