import type { ReactNode } from 'react'

import { View } from '@tarojs/components'

import './index.scss'

export type ChipTone = 'plain' | 'yellow' | 'mint' | 'lav' | 'coral'

export interface ChipProps {
  children?: ReactNode
  tone?: ChipTone
  className?: string
}

/** 小标签：题型 / 难度 / 状态。 */
export default function Chip({ children, tone = 'plain', className = '' }: ChipProps) {
  return <View className={`chip chip-${tone} ${className}`}>{children}</View>
}
