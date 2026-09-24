import { View } from '@tarojs/components'

import { ICON_SVG, type IconName } from '@/assets/icons'
import { svgToDataUri } from '@/utils/svg'

import './index.scss'

export type IconSize = 'sm' | 'md' | 'lg'

export interface IconProps {
  name: IconName
  size?: IconSize
  className?: string
  onClick?: () => void
}

/** 线性图标：20 / 24 / 32（原型「四 · 图标规范」的尺寸令牌）。 */
export default function Icon({ name, size = 'md', className = '', onClick }: IconProps) {
  return (
    <View
      className={`icon icon-${size} ${className}`}
      style={{ backgroundImage: `url("${svgToDataUri(ICON_SVG[name])}")` }}
      onClick={onClick}
    />
  )
}
