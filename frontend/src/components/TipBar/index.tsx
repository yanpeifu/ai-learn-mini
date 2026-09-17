import type { ReactNode } from 'react'

import { Text, View } from '@tarojs/components'

import Icon from '@/components/Icon'

import './index.scss'

export interface TipBarProps {
  children?: ReactNode
  /** 左侧小图标（可选，例如 bulb） */
  icon?: React.ComponentProps<typeof Icon>['name']
  className?: string
}

/** 提示条：暖黄底 + 墨黑描边，用于建议、提醒、引导文案（原型第 6.5 节）。 */
export default function TipBar({ children, icon, className = '' }: TipBarProps) {
  return (
    <View className={`tipbar ${className}`}>
      {icon ? <Icon name={icon} size='sm' className='tipbar-icon' /> : null}
      <Text className='tipbar-text'>{children}</Text>
    </View>
  )
}
