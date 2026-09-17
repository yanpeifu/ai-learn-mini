import type { ReactNode } from 'react'

import { Text, View } from '@tarojs/components'

import ClayButton from '@/components/ClayButton'
import Yanbao, { type YanbaoProps } from '@/components/Yanbao'

import './index.scss'

export interface DialogProps {
  visible: boolean
  title: string
  description?: string
  yanbao?: YanbaoProps['mood']
  children?: ReactNode
  primaryText: string
  secondaryText?: string
  onPrimary?: () => void
  onSecondary?: () => void
}

/** 弹窗：圆角 24 + 硬投影 + 左上角颜宝小表情（原型第 6.5 节）。 */
export default function Dialog({
  visible,
  title,
  description,
  yanbao = 'think',
  children,
  primaryText,
  secondaryText,
  onPrimary,
  onSecondary
}: DialogProps) {
  if (!visible) return null
  return (
    <View className='dialog-overlay'>
      <View className='dialog-pop'>
        <Yanbao mood={yanbao} size='md' />
        <Text className='dialog-title'>{title}</Text>
        {description ? <Text className='dialog-desc'>{description}</Text> : null}
        {children}
        <View className='dialog-actions'>
          <ClayButton variant='primary' onClick={onPrimary}>
            {primaryText}
          </ClayButton>
          {secondaryText ? (
            <View className='dialog-secondary' onClick={onSecondary}>
              <Text>{secondaryText}</Text>
            </View>
          ) : null}
        </View>
      </View>
    </View>
  )
}
