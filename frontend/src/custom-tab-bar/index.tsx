import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'

import Icon from '@/components/Icon'

import './index.scss'

const TABS = [
  { pagePath: '/pages/index/index', text: '首页', icon: 'home' as const },
  { pagePath: '/pages/mine/mine', text: '我的', icon: 'mine' as const }
]

/**
 * 自定义 tabBar：原型底部是「圆角方块图标 + 文字」，微信原生 tabBar 画不出这个手感。
 *
 * 启用方式：把 src/app.config.ts 里的 `tabBar.custom` 改成 true（需要在微信开发者工具里验证一次）。
 * 现在默认仍用原生 tabBar，避免未验证的自定义组件影响编译与真机表现。
 */
export default function CustomTabBar() {
  const [active, setActive] = useState(0)

  useDidShow(() => {
    const pages = Taro.getCurrentPages()
    const current = pages[pages.length - 1]?.route ?? ''
    const index = TABS.findIndex((tab) => current.includes(tab.pagePath.replace(/^\//, '')))
    setActive(index >= 0 ? index : 0)
  })

  return (
    <View className='tabbar'>
      {TABS.map((tab, index) => (
        <View
          key={tab.pagePath}
          className={`tabbar-item ${index === active ? 'tabbar-item-on' : ''}`}
          onClick={() => Taro.switchTab({ url: tab.pagePath })}
        >
          <Icon name={tab.icon} size='sm' />
          <Text className='tabbar-text'>{tab.text}</Text>
        </View>
      ))}
    </View>
  )
}
