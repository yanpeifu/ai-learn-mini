import type { ReactNode } from 'react'

import { View } from '@tarojs/components'
import type { ITouchEvent } from '@tarojs/components'

import './index.scss'

export type ClayButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
export type ClayButtonSize = 'lg' | 'md'

export interface ClayButtonProps {
  children?: ReactNode
  variant?: ClayButtonVariant
  size?: ClayButtonSize
  disabled?: boolean
  block?: boolean
  className?: string
  onClick?: (event: ITouchEvent) => void
}

/**
 * 黏土按钮：2.5px 墨黑描边 + 硬投影；按下时下沉 2px、投影收为 0（风格签名动作）。
 * 橙底/绿底/黄底一律配墨黑字（对比度规则，原型第 3.2 节）。
 */
export default function ClayButton({
  children,
  variant = 'secondary',
  size = 'lg',
  disabled = false,
  block = true,
  className = '',
  onClick
}: ClayButtonProps) {
  return (
    <View
      className={[
        'clay-btn',
        `clay-btn-${variant}`,
        `clay-btn-${size}`,
        block ? 'clay-btn-block' : '',
        disabled ? 'clay-btn-disabled' : '',
        className
      ]
        .filter(Boolean)
        .join(' ')}
      hoverClass={disabled ? 'none' : 'clay-btn-hover'}
      onClick={(event) => {
        if (disabled) return
        onClick?.(event)
      }}
    >
      {children}
    </View>
  )
}
