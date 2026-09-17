import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'

import './app.scss'

import { AttemptProvider } from '@/store/AttemptContext'
import { UserProvider } from '@/store/UserContext'

function App({ children }: PropsWithChildren<any>) {
  useLaunch(() => {
    // 启动即静默登录（PRD F7）；登录逻辑在 UserProvider 里
  })

  return (
    <UserProvider>
      <AttemptProvider>{children}</AttemptProvider>
    </UserProvider>
  )
}

export default App
