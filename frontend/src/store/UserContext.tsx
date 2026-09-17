import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import Taro from '@tarojs/taro'

import { api } from '@/services/api'
import { storage } from '@/services/storage'
import type { UserPublic } from '@/types/api'

interface UserContextValue {
  user: UserPublic | null
  ready: boolean
  login: () => Promise<UserPublic | null>
}

const UserContext = createContext<UserContextValue>({
  user: null,
  ready: false,
  login: async () => null
})

async function resolveLoginCode(): Promise<string> {
  try {
    const result = await Taro.login()
    if (result?.code) return result.code
  } catch {
    /* H5 或未配置 AppID 时会失败，走下面的 DEV 兜底 */
  }
  return storage.getDeviceId()
}

/** 全局用户态：启动时静默登录（PRD F7）。 */
export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null)
  const [ready, setReady] = useState(false)

  const login = useCallback(async () => {
    try {
      const code = await resolveLoginCode()
      const result = await api.login(code)
      storage.setToken(result.token)
      setUser(result.user)
      return result.user
    } catch {
      // 登录失败不阻塞浏览（PRD F7）：后续写操作会再要求登录
      return null
    } finally {
      setReady(true)
    }
  }, [])

  useEffect(() => {
    if (storage.getToken()) {
      setReady(true)
      return
    }
    void login()
  }, [login])

  const value = useMemo(() => ({ user, ready, login }), [user, ready, login])
  return <UserContext.Provider value={value}>{children}</UserContext.Provider>
}

export function useUser(): UserContextValue {
  return useContext(UserContext)
}
