import { View } from '@tarojs/components'

import './index.scss'

export interface ProgressBarProps {
  /** 0–100 */
  percent: number
  className?: string
}

/** 进度条：12px 高、2px 墨黑描边、暖橙填充（原型第 6.4 节）。 */
export default function ProgressBar({ percent, className = '' }: ProgressBarProps) {
  const safe = Math.max(0, Math.min(100, Math.round(percent)))
  return (
    <View className={`prog ${className}`}>
      <View className='prog-fill' style={{ width: `${safe}%` }} />
    </View>
  )
}
