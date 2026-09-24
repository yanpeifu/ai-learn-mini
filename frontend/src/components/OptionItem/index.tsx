import { Text, View } from '@tarojs/components'

import './index.scss'

export type OptionState = 'default' | 'picked' | 'right' | 'wrong' | 'right-answer' | 'dim' | 'disabled'

export interface OptionItemProps {
  optionKey?: string
  text?: string
  state?: OptionState
  /** 右侧角标文案，如「答对了」「你选的」「正确答案」「已选」 */
  tail?: string
  /** judge = 判断题的大块 ✔/✘ 选项 */
  variant?: 'normal' | 'judge'
  onClick?: () => void
}

/**
 * 选项条（答题页最重要的组件，原型第 6.3 节）：
 * 默认 / 已选（暖黄 + 下沉）/ 答对（薄荷绿 + 角标）/ 答错（珊瑚红 + 晃动）/
 * 正确答案高亮 / 其余降透明虚线 / 禁用。
 * 注意：答错时「你选的」和「正确答案」必须同时可见。
 */
export default function OptionItem({
  optionKey,
  text,
  state = 'default',
  tail,
  variant = 'normal',
  onClick
}: OptionItemProps) {
  const classes = [
    'option',
    `option-${state}`,
    variant === 'judge' ? 'option-judge' : '',
    state === 'wrong' ? 'option-shake' : ''
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <View className={classes} onClick={state === 'disabled' ? undefined : onClick}>
      {variant === 'judge' ? (
        <Text className='option-judge-key'>{optionKey}</Text>
      ) : (
        <Text className='option-key'>{optionKey}</Text>
      )}
      {variant === 'judge' ? (
        <Text className='option-judge-text'>{text}</Text>
      ) : (
        <Text className='option-text'>{text}</Text>
      )}
      {tail ? <Text className='option-tail'>{tail}</Text> : null}
    </View>
  )
}
