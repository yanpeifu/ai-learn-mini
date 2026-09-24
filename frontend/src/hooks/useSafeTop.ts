import { useMemo } from 'react'

import Taro from '@tarojs/taro'

/** 自定义导航栏要自己留出状态栏高度（原型每页都自带页头）。 */
export function useSafeTop(): number {
  return useMemo(() => {
    try {
      return Taro.getSystemInfoSync().statusBarHeight ?? 20
    } catch {
      return 20
    }
  }, [])
}
