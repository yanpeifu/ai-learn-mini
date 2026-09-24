import { Text, View } from '@tarojs/components'

import { ICON_SVG, type IconName } from '@/assets/icons'
import { MASCOT_ALT, type YanbaoMood } from '@/assets/mascot'
import {
  Chip,
  ClayButton,
  ClayCard,
  EmptyState,
  Icon,
  OptionItem,
  ProgressBar,
  Skeleton,
  Stepper,
  TipBar,
  Toast,
  Yanbao
} from '@/components'
import type { OptionState } from '@/components'

import './components.scss'

const MOODS: YanbaoMood[] = ['happy', 'think', 'star', 'shy', 'cheer', 'peek', 'sad', 'go']
const ICONS = Object.keys(ICON_SVG) as IconName[]
const OPTION_STATES: OptionState[] = [
  'default',
  'picked',
  'right',
  'wrong',
  'right-answer',
  'dim',
  'disabled'
]

const OPTION_LABELS: Record<OptionState, string> = {
  default: '默认态',
  picked: '已选中',
  right: '答对',
  wrong: '答错（用户选的）',
  'right-answer': '答错时高亮正确答案',
  dim: '提交后其它选项',
  disabled: '禁用'
}

const OPTION_TAILS: Partial<Record<OptionState, string>> = {
  picked: '可改',
  right: '答对了',
  wrong: '你选的',
  'right-answer': '正确答案'
}

/**
 * 组件状态预览页：把《原型-3-状态与规范.html》里的每个组件状态在这里渲染出来，
 * 用于逐状态视觉验收（H5 构建后可直接截图比对）。**发布前必须删除这个页面。**
 */
export default function DevComponents() {
  return (
    <View className='dev-page'>
      <Text className='dev-h1'>一 · 颜宝表情包（8 个）</Text>
      <View className='dev-grid4'>
        {MOODS.map((mood) => (
          <View className='dev-cell' key={mood}>
            <Yanbao mood={mood} size='sm' />
            <Text className='dev-label'>{MASCOT_ALT[mood]}</Text>
          </View>
        ))}
      </View>

      <Text className='dev-h1'>二 · 按钮（主 / 次 / 危险 / 文字 / 禁用 / 并排）</Text>
      <ClayCard>
        <View className='dev-stack'>
          <ClayButton variant='primary'>开始生成</ClayButton>
          <ClayButton>重新生成</ClayButton>
          <ClayButton variant='danger'>删 除</ClayButton>
          <ClayButton variant='ghost' block={false}>
            跳过，直接看讲解
          </ClayButton>
          <ClayButton disabled>开始生成</ClayButton>
          <View className='clay-btnrow'>
            <ClayButton size='md'>返回</ClayButton>
            <ClayButton size='md' variant='primary'>
              确定
            </ClayButton>
          </View>
        </View>
      </ClayCard>

      <Text className='dev-h1'>三 · 选项条（答题页核心组件）</Text>
      <View className='dev-stack'>
        {OPTION_STATES.map((state) => (
          <OptionItem
            key={state}
            optionKey='A'
            text={OPTION_LABELS[state]}
            state={state}
            tail={OPTION_TAILS[state]}
          />
        ))}
        <View className='option-row'>
          <OptionItem variant='judge' optionKey='✓' text='正确' />
          <OptionItem variant='judge' optionKey='✕' text='错误' />
        </View>
      </View>

      <Text className='dev-h1'>四 · 标签与进度</Text>
      <View className='dev-stack'>
        <View className='chip-row'>
          <Chip tone='yellow'>单选题</Chip>
          <Chip tone='mint'>难度 ★★☆</Chip>
          <Chip tone='lav'>第 2 关</Chip>
          <Chip tone='coral'>再看看</Chip>
          <Chip>内容由 AI 生成</Chip>
        </View>
        <ProgressBar percent={20} />
        <ProgressBar percent={62} />
        <ProgressBar percent={100} />
        <Stepper steps={['① 理解内容', '② 梳理结构', '③ 准备出题']} activeIndex={1} />
      </View>

      <Text className='dev-h1'>五 · 卡片层级与提示条</Text>
      <View className='dev-stack'>
        <ClayCard level={1}>
          <Text className='dev-label'>一级卡片（硬投影）：用于列表项、选项条</Text>
        </ClayCard>
        <ClayCard level={2}>
          <Text className='dev-label'>二级卡片（硬投影 + 柔光 + 内高光）：用于输入区、题干、弹窗</Text>
        </ClayCard>
        <TipBar icon='bulb'>可以直接粘贴一段讲义，或者写上你想了解的三个问题</TipBar>
        <Toast visible>内容太短啦，再多描述一点（至少 20 字）</Toast>
      </View>

      <Text className='dev-h1'>六 · 空状态与异常态</Text>
      <View className='dev-stack'>
        <ClayCard>
          <EmptyState title='这里还空着' description='去闯第一关，记录就会出现在这里' actionText='去学习' />
        </ClayCard>
        <ClayCard>
          <EmptyState
            yanbao='sad'
            title='网络打了个盹'
            description='检查一下网络，然后点一下重试'
            actionText='重 试'
          />
        </ClayCard>
        <ClayCard>
          <EmptyState
            yanbao='shy'
            title='这次没生成成功'
            description='可能是内容太长或格式特殊，换个说法再试试？'
            actionText='再试一次'
          />
        </ClayCard>
      </View>

      <Text className='dev-h1'>七 · 骨架屏</Text>
      <Skeleton lines={4} />

      <Text className='dev-h1'>八 · 图标（{ICONS.length} 个）</Text>
      <ClayCard>
        <View className='dev-grid4'>
          {ICONS.map((name) => (
            <View className='dev-cell' key={name}>
              <Icon name={name} size='md' />
              <Text className='dev-label'>{name}</Text>
            </View>
          ))}
        </View>
      </ClayCard>
    </View>
  )
}
