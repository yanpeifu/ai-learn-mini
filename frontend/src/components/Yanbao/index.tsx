import { View } from '@tarojs/components'

import { MASCOT_ALT, MASCOT_SVG, type YanbaoMood } from '@/assets/mascot'
import { svgToDataUri } from '@/utils/svg'

import './index.scss'

export type YanbaoSize = 'xs' | 'sm' | 'md' | 'lg'

export interface YanbaoProps {
  mood?: YanbaoMood
  size?: YanbaoSize
  className?: string
}

/** 颜宝：8 个表情，尺寸 xs34 / sm56 / md78 / lg92（与原型一致）。 */
export default function Yanbao({ mood = 'happy', size = 'sm', className = '' }: YanbaoProps) {
  return (
    <View
      className={`yanbao yanbao-${size} ${className}`}
      style={{ backgroundImage: `url("${svgToDataUri(MASCOT_SVG[mood])}")` }}
      aria-label={MASCOT_ALT[mood]}
    />
  )
}
