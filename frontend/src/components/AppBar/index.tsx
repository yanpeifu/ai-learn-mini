import type { ReactNode } from 'react'

import { Text, View } from '@tarojs/components'

import Icon from '@/components/Icon'
import { useNavMetrics } from '@/hooks/useNavMetrics'

import './index.scss'

export interface AppBarProps {
  title: string
  showBack?: boolean
  /** 右侧内容，原型里是「⋯」（举报入口） */
  right?: ReactNode
  onBack?: () => void
}

/** 页头：状态栏安全区 + 返回 + 标题 + 右侧操作（对应原型 .appbar）。 */
export default function AppBar({ title, showBack = true, right, onBack }: AppBarProps) {
  const { safeTop, rightGap, barHeight } = useNavMetrics()
  return (
    <View className='appbar-wrap'>
      <View className='appbar-safe' style={{ height: `${safeTop}px` }} />
      <View
        className='appbar'
        style={{ minHeight: `${barHeight}px`, paddingRight: `${rightGap}px` }}
      >
        {showBack ? (
          <View className='appbar-back' onClick={onBack}>
            <Icon name='back' size='md' />
          </View>
        ) : null}
        <Text className='appbar-title'>{title}</Text>
        <View className='appbar-right'>{right}</View>
      </View>
    </View>
  )
}
