import { Text, View } from '@tarojs/components'

import ClayButton from '@/components/ClayButton'
import Yanbao, { type YanbaoProps } from '@/components/Yanbao'

import './index.scss'

export interface EmptyStateProps {
  yanbao?: YanbaoProps['mood']
  title: string
  description?: string
  actionText?: string
  onAction?: () => void
  /** dashed = 首页那种虚线引导框（P1-1）；plain = 普通空状态 */
  variant?: 'dashed' | 'plain'
  className?: string
}

/** 空状态 / 网络错误 / 生成失败：所有异常都要有出口，不能是死胡同。 */
export default function EmptyState({
  yanbao = 'peek',
  title,
  description,
  actionText,
  onAction,
  variant = 'plain',
  className = ''
}: EmptyStateProps) {
  return (
    <View className={`empty empty-${variant} ${className}`}>
      <Yanbao mood={yanbao} size={variant === 'dashed' ? 'sm' : 'md'} />
      <Text className='empty-title'>{title}</Text>
      {description ? <Text className='empty-desc'>{description}</Text> : null}
      {actionText ? (
        <ClayButton variant='primary' block={false} className='empty-action' onClick={onAction}>
          {actionText}
        </ClayButton>
      ) : null}
    </View>
  )
}
