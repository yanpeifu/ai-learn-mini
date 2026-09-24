import { View } from '@tarojs/components'

import './index.scss'

export interface SkeletonProps {
  /** 骨架条数（原型大纲生成中是 4 条） */
  lines?: number
  className?: string
}

/** 骨架屏：圆形序号 + shimmer 线（原型 P2-1）。 */
export default function Skeleton({ lines = 4, className = '' }: SkeletonProps) {
  const widths = ['100%', '70%', '85%', '55%']
  return (
    <View className={`skl-wrap ${className}`}>
      {Array.from({ length: lines }).map((_item, index) => (
        <View className='skl' key={index}>
          <View className='skl-dot' />
          <View className='skl-line' style={{ width: widths[index % widths.length] }} />
        </View>
      ))}
    </View>
  )
}
