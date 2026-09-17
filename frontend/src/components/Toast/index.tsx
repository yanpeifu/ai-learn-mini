import type { ReactNode } from 'react'

import { Text, View } from '@tarojs/components'

import './index.scss'

export interface ToastProps {
  visible: boolean
  children?: ReactNode
  className?: string
}

/** 错误/警告提示条（珊瑚红底，原型 P1-3 的「内容太短啦…」）。 */
export default function Toast({ visible, children, className = '' }: ToastProps) {
  if (!visible) return null
  return (
    <View className={`toast ${className}`}>
      <Text>{children}</Text>
    </View>
  )
}
