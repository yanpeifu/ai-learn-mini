import { Text, View } from '@tarojs/components'

import './index.scss'

export interface StepperProps {
  steps: string[]
  /** 当前高亮到第几步（0 开始） */
  activeIndex: number
  className?: string
}

/** 三步进度指示（原型 P2-1：① 理解内容 ② 梳理结构 ③ 准备出题）。 */
export default function Stepper({ steps, activeIndex, className = '' }: StepperProps) {
  return (
    <View className={`stepper ${className}`}>
      {steps.map((step, index) => (
        <Text key={step} className={`stepper-item ${index === activeIndex ? 'stepper-on' : ''}`}>
          {step}
        </Text>
      ))}
    </View>
  )
}
