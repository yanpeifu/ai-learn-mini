import { Navigator, ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useCallback, useState } from 'react'

import type { IconName } from '@/assets/icons'
import { ClayButton, EmptyState, Icon, TipBar, Toast, Yanbao } from '@/components'
import { COPY } from '@/constants/copy'
import { useNavMetrics } from '@/hooks/useNavMetrics'
import { api } from '@/services/api'
import { storage } from '@/services/storage'
import { useUser } from '@/store/UserContext'
import type { AttemptHistoryItem, OngoingAttempt, TemplateItem } from '@/types/api'

import './index.scss'

const MIN_CHARS = 20
const MAX_CHARS = 2000
const RECENT_LIMIT = 3

const TEMPLATE_ICONS: Record<string, IconName> = {
  chart: 'chart',
  law: 'law',
  book: 'book',
  language: 'language',
  code: 'code',
  edit: 'edit'
}

/** P1 首页：空态（P1-1）/ 学习中（P1-2）/ 输入校验错误（P1-3）。 */
export default function Index() {
  const { login } = useUser()
  const { safeTop, rightGap } = useNavMetrics()
  const [text, setText] = useState('')
  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [records, setRecords] = useState<AttemptHistoryItem[]>([])
  const [ongoing, setOngoing] = useState<OngoingAttempt | null>(null)
  const [recordsLoaded, setRecordsLoaded] = useState(false)

  const trimmed = text.trim()
  const count = trimmed.length
  // 实时校验（原型 P1-3：字数不合法时输入框变红 + 提示 + 主按钮置灰）
  const error: 'short' | 'long' | null =
    count > 0 && count < MIN_CHARS ? 'short' : count > MAX_CHARS ? 'long' : null
  const showError = error !== null
  const canSubmit = count >= MIN_CHARS && count <= MAX_CHARS

  const loadHome = useCallback(async () => {
    if (templates.length === 0) {
      try {
        const result = await api.templates()
        setTemplates(result.templates)
      } catch {
        /* 模板拿不到不影响输入 */
      }
    }
    try {
      if (!storage.getToken()) await login()
      const [history, running] = await Promise.all([
        api.attempts(1, RECENT_LIMIT),
        api.ongoingAttempt()
      ])
      setRecords(history.list)
      setOngoing(running.attempt)
    } catch {
      setRecords([])
      setOngoing(null)
    } finally {
      setRecordsLoaded(true)
    }
  }, [login, templates.length])

  useDidShow(() => {
    void loadHome()
  })

  const onPickTemplate = (template: TemplateItem) => {
    setText(template.prefill)
  }

  const onGenerate = () => {
    if (!canSubmit) return
    storage.setPendingText(trimmed)
    Taro.navigateTo({ url: '/pages/outline/outline?mode=generate' })
  }

  const scoreClass = (accuracy: number) =>
    accuracy >= 90 ? 'score-good' : accuracy >= 70 ? 'score-mid' : 'score-bad'

  return (
    <View className='page-index' style={{ paddingTop: `${safeTop + 13}px` }}>
      <View className='home-head' style={{ paddingRight: `${rightGap}px` }}>
        <View className='home-head-text'>
          <Text className='h1'>{COPY.homeTitle}</Text>
          <Text className='cap'>{COPY.homeSubtitle}</Text>
        </View>
        <Yanbao mood={showError ? 'think' : 'happy'} size='sm' />
      </View>

      <View className={`input-card ${showError ? 'input-card-err' : ''}`}>
        <Textarea
          className='input-area'
          value={text}
          maxlength={MAX_CHARS}
          placeholder={COPY.inputPlaceholder}
          placeholderClass='input-placeholder'
          autoHeight={false}
          onInput={(event) => {
            setText(event.detail.value)
          }}
        />
        <Text className={`counter ${count > MAX_CHARS ? 'counter-bad' : ''}`}>
          {count} / {MAX_CHARS}
        </Text>
      </View>

      <Toast visible={error === 'short'}>{COPY.tooShort}</Toast>
      <Toast visible={error === 'long'}>{COPY.tooLong}</Toast>
      {showError ? <TipBar icon='bulb'>可以直接粘贴一段讲义，或者写上你想了解的三个问题</TipBar> : null}

      <Text className='sec'>{COPY.tryThese}</Text>
      <ScrollView scrollX className='tpl-scroll' showScrollbar={false}>
        {templates.map((template) => (
          <View className='tpl' key={template.id} onClick={() => onPickTemplate(template)}>
            <Icon name={TEMPLATE_ICONS[template.icon] ?? 'edit'} size='md' />
            <Text className='tpl-name'>{template.name}</Text>
          </View>
        ))}
      </ScrollView>

      <ClayButton variant='primary' disabled={!canSubmit} onClick={onGenerate}>
        {COPY.startGenerate}
      </ClayButton>

      {ongoing ? (
        <View
          className='resume'
          onClick={() => Taro.navigateTo({ url: `/pages/quiz/quiz?attemptId=${ongoing.attempt_id}` })}
        >
          <View className='resume-play'>
            <Icon name='play' size='sm' />
          </View>
          <View className='resume-text'>
            <Text className='resume-title'>{COPY.resumeLearning}</Text>
            <Text className='cap'>
              {ongoing.title} · 已完成 {ongoing.answered_count}/{ongoing.total_count}
            </Text>
          </View>
          <Text className='resume-arrow'>›</Text>
        </View>
      ) : null}

      {records.length > 0 ? (
        <View className='recent'>
          <Text className='sec'>{COPY.recentLearning}</Text>
          {records.map((record) => (
            <Navigator
              className='rec'
              hoverClass='rec-hover'
              key={record.attempt_id}
              url={`/pages/result/result?attemptId=${record.attempt_id}`}
            >
              <Text className='rec-title'>{record.title}</Text>
              <Text className={`score ${scoreClass(record.accuracy)}`}>{Math.round(record.accuracy)}%</Text>
              <Text className='rec-arrow'>›</Text>
            </Navigator>
          ))}
        </View>
      ) : recordsLoaded ? (
        <View className='home-empty'>
          <EmptyState
            variant='dashed'
            yanbao='peek'
            title={COPY.emptyRecords}
            description={COPY.emptyRecordsHint}
          />
        </View>
      ) : null}
    </View>
  )
}
