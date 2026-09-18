import { Text, Textarea, View } from '@tarojs/components'
import type { ITouchEvent } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { useCallback, useRef, useState } from 'react'

import { AppBar, ClayButton, Icon, Skeleton, Stepper, TipBar, Toast, Yanbao } from '@/components'
import { COPY } from '@/constants/copy'
import { ApiError } from '@/services/request'
import { api } from '@/services/api'
import { storage } from '@/services/storage'
import type { OutlinePoint } from '@/types/api'

import './outline.scss'

type PageState = 'generating' | 'editing' | 'failed'

/** P2 知识大纲：生成中（P2-1）/ 可编辑（P2-2）/ 生成失败（P2-3）。 */
export default function Outline() {
  const [state, setState] = useState<PageState>('generating')
  const [stepIndex, setStepIndex] = useState(0)
  const [tipIndex, setTipIndex] = useState(0)
  const [outlineId, setOutlineId] = useState(0)
  const [points, setPoints] = useState<OutlinePoint[]>([])
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [swipedIndex, setSwipedIndex] = useState<number | null>(null)
  const [failedMessage, setFailedMessage] = useState<string>(COPY.outlineFailedHint)
  const [toast, setToast] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const sourceText = useRef('')
  const touchStartX = useRef(0)

  const generate = useCallback(async (text: string) => {
    setState('generating')
    setStepIndex(0)
    setTipIndex(0)
    const stepTimer = setInterval(() => setStepIndex((index) => (index + 1) % 3), 4000)
    const tipTimer = setInterval(() => setTipIndex((index) => (index + 1) % 3), 2500)
    try {
      const result = await api.generateOutline(text)
      setOutlineId(result.outline_id)
      setPoints(result.points)
      setState('editing')
    } catch (error) {
      // 不暴露技术细节，只给可执行的下一步（原型 P2-3）
      setFailedMessage(error instanceof ApiError ? error.message : COPY.outlineFailedHint)
      setState('failed')
    } finally {
      clearInterval(stepTimer)
      clearInterval(tipTimer)
    }
  }, [])

  useLoad(() => {
    const text = storage.getPendingText()
    sourceText.current = text
    if (!text) {
      setFailedMessage('没有拿到要学习的内容，回首页重新输入一次吧')
      setState('failed')
      return
    }
    void generate(text)
  })

  const flash = (message: string) => {
    setToast(message)
    setTimeout(() => setToast(''), 1800)
  }

  const onEditConfirm = async (index: number, title: string) => {
    const next = points.map((point, position) =>
      position === index ? { ...point, title: title.trim() || point.title } : point
    )
    setPoints(next)
    setEditingIndex(null)
    try {
      await api.saveOutline(outlineId, next)
    } catch {
      flash('保存没成功，等下再试一次')
    }
  }

  const onDelete = async (index: number) => {
    if (points.length <= 2) {
      flash(COPY.outlineDeleteBlocked)
      setSwipedIndex(null)
      return
    }
    const next = points.filter((_point, position) => position !== index)
    setPoints(next)
    setSwipedIndex(null)
    try {
      await api.saveOutline(outlineId, next)
    } catch {
      flash('删除没同步成功，等下再试一次')
    }
  }

  const onStartQuiz = async () => {
    setSubmitting(true)
    try {
      await api.saveOutline(outlineId, points)
      await api.generateLevels(outlineId)
      const started = await api.startAttempt(outlineId)
      storage.clearPendingText()
      Taro.redirectTo({ url: `/pages/quiz/quiz?attemptId=${started.attempt_id}` })
    } catch (error) {
      flash(error instanceof ApiError ? error.message : '出题没成功，再试一次？')
    } finally {
      setSubmitting(false)
    }
  }

  const goBack = () => Taro.navigateBack()

  return (
    <View className='page-outline'>
      <AppBar title={COPY.outlineTitle} onBack={goBack} />

      {state === 'generating' ? (
        <View className='content content-center'>
          <Yanbao mood='think' size='md' />
          <Text className='gen-title'>{COPY.generatingTitle}</Text>
          <Text className='cap'>{COPY.generatingTips[tipIndex]}</Text>
          <Text className='cap'>{COPY.generatingHint}</Text>
          <Stepper steps={[...COPY.generatingSteps]} activeIndex={stepIndex} />
          <Skeleton lines={4} />
          <TipBar>这一步会先把知识拆成 3–5 个知识点，你可以改完再出题</TipBar>
        </View>
      ) : null}

      {state === 'editing' ? (
        <View className='content'>
          <TipBar>{COPY.outlineReadyTip.replace('{n}', String(points.length))}</TipBar>
          {points.map((point, index) => (
            <View
              className={`kp ${editingIndex === index ? 'kp-editing' : ''} ${
                swipedIndex === index ? 'kp-swiping' : ''
              }`}
              key={point.id}
              onTouchStart={(event) => {
                const touch = (event as ITouchEvent).touches[0]
                touchStartX.current = touch?.clientX ?? 0
              }}
              onTouchMove={(event) => {
                const touch = (event as ITouchEvent).touches[0]
                const current = touch?.clientX ?? 0
                if (touchStartX.current - current > 30) setSwipedIndex(index)
              }}
              onTouchEnd={() => touchStartX.current = 0}
            >
              <Text className='kp-index'>{index + 1}</Text>
              <View className='kp-body'>
                {editingIndex === index ? (
                  <Textarea
                    className='kp-input'
                    value={point.title}
                    maxlength={30}
                    autoFocus
                    autoHeight
                    onBlur={(event) => onEditConfirm(index, event.detail.value)}
                  />
                ) : (
                  <Text className='kp-title' onClick={() => setEditingIndex(index)}>
                    {point.title}
                  </Text>
                )}
                <Text className={`cap ${editingIndex === index ? 'kp-editing-hint' : ''}`}>
                  {editingIndex === index ? COPY.outlineEditingHint : point.summary}
                </Text>
              </View>
              {editingIndex === index ? (
                <Icon name='check' size='md' onClick={() => setEditingIndex(null)} />
              ) : (
                <Icon name='close' size='md' className='kp-remove' onClick={() => onDelete(index)} />
              )}
              {swipedIndex === index ? (
                <View className='kp-delete' onClick={() => onDelete(index)}>
                  <Text>删除</Text>
                </View>
              ) : null}
            </View>
          ))}
          <Text className='cap kp-note'>左滑出现删除；剩余不足 2 个时禁止再删并提示</Text>
          <View className='btnrow'>
            <ClayButton onClick={() => generate(sourceText.current)}>{COPY.regenerate}</ClayButton>
            <ClayButton variant='primary' onClick={onStartQuiz}>
              {COPY.startQuiz}
            </ClayButton>
          </View>
        </View>
      ) : null}

      {state === 'failed' ? (
        <View className='content content-center'>
          <Yanbao mood='sad' size='lg' />
          <Text className='gen-title'>{COPY.outlineFailedTitle}</Text>
          <Text className='cap gen-hint'>{failedMessage}</Text>
          <TipBar>
            <Text className='tip-strong'>{COPY.outlineFailedTryTitle}</Text>
            {'\n'}· {COPY.outlineFailedTry[0]}
            {'\n'}· {COPY.outlineFailedTry[1]}
          </TipBar>
          <View className='btnrow btnrow-full'>
            <ClayButton onClick={goBack}>{COPY.changeContent}</ClayButton>
            <ClayButton variant='primary' onClick={() => generate(sourceText.current)}>
              {COPY.tryAgain}
            </ClayButton>
          </View>
        </View>
      ) : null}

      <Toast visible={Boolean(toast)} className='outline-toast'>
        {toast}
      </Toast>

      {submitting ? (
        <View className='dialog-overlay'>
          <View className='dialog-pop submitting'>
            <Yanbao mood='think' size='md' />
            <Text className='gen-title'>{COPY.submitting}</Text>
            <Text className='cap'>{COPY.submittingHint}</Text>
          </View>
        </View>
      ) : null}
    </View>
  )
}
