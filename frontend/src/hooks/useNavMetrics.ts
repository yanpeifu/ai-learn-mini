import { useMemo } from 'react'

import Taro from '@tarojs/taro'

export interface NavMetrics {
  /** 状态栏高度（px） */
  safeTop: number
  /** 右上角需要给微信胶囊按钮让出的宽度（px） */
  rightGap: number
  /** 自定义导航栏内容区高度（px，不含状态栏） */
  barHeight: number
}

const FALLBACK: NavMetrics = { safeTop: 20, rightGap: 16, barHeight: 44 }

/**
 * 计算自定义导航栏的安全尺寸（Bug 修复：右上角被原生胶囊按钮遮挡）。
 *
 * 微信右上角的「胶囊按钮」由原生绘制、**永远在最上层**，
 * 自定义导航栏必须按它的实际位置留出右侧空间，否则标题/操作按钮会被盖住；
 * 高度也按胶囊的上下留白推算，视觉上才能和原生导航栏对齐。
 */
export function useNavMetrics(): NavMetrics {
  return useMemo(() => {
    try {
      const info = Taro.getSystemInfoSync()
      const windowWidth = info.windowWidth ?? 375
      const safeTop = info.statusBarHeight ?? FALLBACK.safeTop
      // H5 上没有这个 API，会走兜底分支
      const rect = Taro.getMenuButtonBoundingClientRect?.()
      if (!rect || !rect.width) {
        return { ...FALLBACK, safeTop }
      }
      const gap = Math.max(4, rect.top - safeTop)
      return {
        safeTop,
        rightGap: Math.max(FALLBACK.rightGap, Math.round(windowWidth - rect.left + 8)),
        barHeight: Math.round(rect.height + gap * 2)
      }
    } catch {
      return FALLBACK
    }
  }, [])
}
