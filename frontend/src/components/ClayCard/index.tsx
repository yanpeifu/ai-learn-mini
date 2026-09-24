import type { CSSProperties, ReactNode } from 'react'

import { View } from '@tarojs/components'

import './index.scss'

export interface ClayCardProps {
  children?: ReactNode
  /** 1 = 一级卡片（仅硬投影，用于列表项/选项条）；2 = 二级卡片（硬投影 + 柔光 + 内高光） */
  level?: 1 | 2
  className?: string
  style?: CSSProperties
  onClick?: () => void
}

export default function ClayCard({
  children,
  level = 2,
  className = '',
  style,
  onClick
}: ClayCardProps) {
  return (
    <View className={`clay-card clay-card-l${level} ${className}`} style={style} onClick={onClick}>
      {children}
    </View>
  )
}
