import { Text, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { useMemo, useRef, useState } from 'react'

import { AppBar, Chip, ClayButton, Dialog, OptionItem, ProgressBar, TipBar, Yanbao } from '@/components'
import type { OptionState } from '@/components'
import { COPY } from '@/constants/copy'
import { api } from '@/services/api'
import { feedback } from '@/services/feedback'
import { ApiError } from '@/services/request'
import type { AnswerResult, ReviewLevel, ReviewQuestion } from '@/types/api'

import './quiz.scss'

const TYPE_LABELS: Record<string, { text: string; tone: 'yellow' | 'lav' | 'mint' }> = {
  single: { text: '单选题', tone: 'yellow' },
  multiple: { text: '多选题', tone: 'lav' },
  judge: { text: '判断题', tone: 'mint' }
}

function difficultyStars(difficulty: number): string {
  if (difficulty <= 2) return '★☆☆'
  if (difficulty === 3) return '★★☆'
  return '★★★'
}

const REPORT_REASONS = ['wrong_answer', 'unclear', 'duplicate', 'other'] as const

/** P3 答题闯关：单选（P3-1）/ 答对（P3-2）/ 答错（P3-3）/ 多选（P3-4）/ 判断（P3-5）/ 连对（P3-6）/ 退出（P3-7）/ 举报（P3-8）。 */
export default function Quiz() {
  const [attemptId, setAttemptId] = useState(0)
  const [outlineTitle, setOutlineTitle] = useState('')
  const [levels, setLevels] = useState<ReviewLevel[]>([])
  const [levelIndex, setLevelIndex] = useState(0)
  const [questionIndex, setQuestionIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [picked, setPicked] = useState<string[]>([])
  const [judgments, setJudgments] = useState<Record<number, AnswerResult>>({})
  const [combo, setCombo] = useState(0)
  const [toast, setToast] = useState('')
  const [quitVisible, setQuitVisible] = useState(false)
  const [reportVisible, setReportVisible] = useState(false)
  const [reportIndex, setReportIndex] = useState(0)
  const questionStart = useRef(Date.now())

  const level = levels[levelIndex]
  const questions = level?.questions ?? []
  const question: ReviewQuestion | undefined = questions[questionIndex]
  const judgment = question ? judgments[question.id] : undefined
  const judged = Boolean(judgment) || Boolean(question?.answered)

  const correctKeys = useMemo(
    () => (judgment ? judgment.correct_answer : question?.correct_answer ?? []),
    [judgment, question]
  )
  const explanation = judgment ? judgment.explanation : question?.explanation ?? ''

  const flash = (message: string) => {
    setToast(message)
    setTimeout(() => setToast(''), 1800)
  }

  const loadAttempt = async (id: number) => {
    try {
      const detail = await api.attemptDetail(id)
      setLevels(detail.levels)
      setOutlineTitle(detail.attempt.title)
      let targetLevel = 0
      let targetQuestion = 0
      let found = false
      detail.levels.forEach((item, levelPosition) => {
        item.questions.forEach((one, questionPosition) => {
          if (!found && !one.answered) {
            targetLevel = levelPosition
            targetQuestion = questionPosition
            found = true
          }
        })
      })
      setLevelIndex(targetLevel)
      setQuestionIndex(targetQuestion)
      questionStart.current = Date.now()
    } catch (error) {
      flash(error instanceof ApiError ? error.message : '题目加载失败，稍后再试')
    } finally {
      setLoading(false)
    }
  }

  useLoad((params) => {
    const id = Number(params?.attemptId ?? 0)
    setAttemptId(id)
    feedback.preloadSounds()
    if (id) {
      void loadAttempt(id)
      return
    }
    void api
      .ongoingAttempt()
      .then((result) => {
        if (!result.attempt) throw new Error('没有进行中的闯关')
        setAttemptId(result.attempt.attempt_id)
        return loadAttempt(result.attempt.attempt_id)
      })
      .catch(() => {
        setLoading(false)
        flash('没有找到这次闯关，回首页重新开始吧')
      })
  })

  const onPick = (key: string) => {
    if (!question || judged) return
    if (question.type === 'multiple') {
      setPicked((current) =>
        current.includes(key) ? current.filter((item) => item !== key) : [...current, key]
      )
      return
    }
    setPicked([key])
  }

  const onSubmit = async () => {
    if (!question || picked.length === 0) return
    try {
      const elapsed = Date.now() - questionStart.current
      const result = await api.submitAnswer(attemptId, question.id, picked, elapsed)
      setJudgments((current) => ({ ...current, [question.id]: result }))
      setCombo(result.combo)
      if (result.is_correct) {
        feedback.play('right')
        feedback.vibrate('light')
        if (result.combo >= 3) {
          feedback.play('combo')
          feedback.vibrate('medium')
        }
      } else {
        feedback.play('wrong')
      }
    } catch (error) {
      flash(error instanceof ApiError ? error.message : '提交没成功，再试一次')
    }
  }

  const goNext = async () => {
    setPicked([])
    setCombo(0)
    questionStart.current = Date.now()
    if (questionIndex < questions.length - 1) {
      setQuestionIndex(questionIndex + 1)
      return
    }
    if (levelIndex < levels.length - 1) {
      setLevelIndex(levelIndex + 1)
      setQuestionIndex(0)
      return
    }
    try {
      await api.finishAttempt(attemptId)
      feedback.play('finish')
      Taro.redirectTo({ url: `/pages/result/result?attemptId=${attemptId}` })
    } catch (error) {
      flash(error instanceof ApiError ? error.message : '结算没成功，再试一次')
    }
  }

  const isPickedKey = (key: string) =>
    picked.includes(key) || (question?.user_answer ?? []).includes(key)

  const optionState = (key: string): OptionState => {
    if (!judged) return picked.includes(key) ? 'picked' : 'default'
    const isCorrectKey = correctKeys.includes(key)
    if (isCorrectKey) return isPickedKey(key) ? 'right' : 'right-answer'
    return isPickedKey(key) ? 'wrong' : 'dim'
  }

  const optionTail = (key: string): string | undefined => {
    if (!judged) return picked.includes(key) ? '可改' : undefined
    const isCorrectKey = correctKeys.includes(key)
    if (isCorrectKey && isPickedKey(key)) return '答对了'
    if (isCorrectKey) return '正确答案'
    if (isPickedKey(key)) return '你选的'
    return undefined
  }

  const tipText = judged
    ? '看完讲解，点下面的按钮继续'
    : question?.type === 'multiple'
      ? `多选题：全对才算对，目前选了 ${picked.length} 项`
      : picked.length > 0
        ? `已选 ${picked[0]}，提交前还可以改`
        : question?.type === 'judge'
          ? '判断题只有两个选项，选完直接提交'
          : '先选一个答案，再点提交'

  const isCorrectNow = judgment ? judgment.is_correct : Boolean(question?.is_correct)

  if (loading) {
    return (
      <View className='page-quiz page-quiz-center'>
        <Yanbao mood='think' size='md' />
        <Text className='cap'>题目马上就来…</Text>
      </View>
    )
  }

  return (
    <View className='page-quiz'>
      <AppBar
        title={level ? `第 ${level.seq} 关 · ${questionIndex + 1} / ${questions.length}` : outlineTitle}
        onBack={() => setQuitVisible(true)}
        right={<Text className='quiz-more' onClick={() => setReportVisible(true)}>⋯</Text>}
      />

      <View className='content'>
        <ProgressBar percent={questions.length ? ((questionIndex + 1) / questions.length) * 100 : 0} />

        <View className='chip-row'>
          <Chip tone={TYPE_LABELS[question?.type ?? 'single'].tone}>
            {TYPE_LABELS[question?.type ?? 'single'].text}
          </Chip>
          {question ? <Chip>难度 {difficultyStars(question.difficulty)}</Chip> : null}
          {judged ? <Chip tone={isCorrectNow ? 'mint' : 'coral'}>{isCorrectNow ? '答对了' : '再看看'}</Chip> : null}
        </View>

        {combo >= 3 ? (
          <View className='combo'>
            <View className='combo-num'>
              <Text className='combo-big'>{combo}</Text>
              <Text className='cap'>连对</Text>
            </View>
            <View className='combo-text'>
              <Text className='combo-title'>手感不错！</Text>
              <Text className='cap'>继续这样答，这一关很快就拿下了</Text>
            </View>
            <Yanbao mood='cheer' size='sm' />
          </View>
        ) : null}

        <View className='stem'>{question?.stem}</View>

        {question?.type === 'judge' ? (
          <View className='option-row'>
            {question.options.map((option) => (
              <OptionItem
                key={option.key}
                variant='judge'
                optionKey={option.text === '正确' ? '✓' : '✕'}
                text={option.text}
                state={optionState(option.key)}
                tail={optionTail(option.key)}
                onClick={() => onPick(option.key)}
              />
            ))}
          </View>
        ) : (
          <View className='option-list'>
            {question?.options.map((option) => (
              <OptionItem
                key={option.key}
                optionKey={option.key}
                text={option.text}
                state={optionState(option.key)}
                tail={optionTail(option.key)}
                onClick={() => onPick(option.key)}
              />
            ))}
          </View>
        )}

        {judged ? (
          <View className='explain'>
            <Text className={`explain-title ${isCorrectNow ? 'explain-ok' : ''}`}>
              {isCorrectNow ? COPY.correctFeedback : COPY.wrongFeedback}
            </Text>
            <Text className='explain-text'>{explanation}</Text>
            <Text className='explain-tiny'>{COPY.aiNotice}</Text>
          </View>
        ) : null}

        <TipBar icon='bulb'>{tipText}</TipBar>

        {judged ? (
          <ClayButton variant='primary' onClick={goNext}>
            {questionIndex === questions.length - 1 && levelIndex === levels.length - 1
              ? COPY.finishLevel
              : COPY.nextQuestion}
          </ClayButton>
        ) : (
          <ClayButton variant='primary' disabled={picked.length === 0} onClick={onSubmit}>
            {COPY.submit}
          </ClayButton>
        )}
      </View>

      <Dialog
        visible={quitVisible}
        yanbao='think'
        title={COPY.quitTitle}
        description={COPY.quitHint}
        primaryText={COPY.quitContinue}
        secondaryText={COPY.quitLater}
        onPrimary={() => setQuitVisible(false)}
        onSecondary={() => {
          setQuitVisible(false)
          Taro.navigateBack()
        }}
      >
        <View className='quit-progress'>
          <Text className='cap'>{COPY.quitCurrent}</Text>
          <Text className='quit-progress-text'>
            第 {level?.seq ?? 1} 关 · {questionIndex + 1} / {questions.length}
          </Text>
        </View>
      </Dialog>

      <Dialog
        visible={reportVisible}
        yanbao='happy'
        title={COPY.reportTitle}
        description={COPY.reportHint}
        primaryText={COPY.reportSubmit}
        secondaryText={COPY.reportCancel}
        onPrimary={async () => {
          try {
            await api.reportQuestion(question?.id ?? 0, REPORT_REASONS[reportIndex])
            setReportVisible(false)
            flash(COPY.reportThanks)
          } catch (error) {
            flash(error instanceof ApiError ? error.message : '反馈没提交成功')
          }
        }}
        onSecondary={() => setReportVisible(false)}
      >
        <View className='report-list'>
          {COPY.reportReasons.map((reason, index) => (
            <View
              className={`radio ${index === reportIndex ? 'radio-on' : ''}`}
              key={reason}
              onClick={() => setReportIndex(index)}
            >
              <View className='radio-dot' />
              <Text>{reason}</Text>
            </View>
          ))}
        </View>
      </Dialog>

      {toast ? (
        <View className='quiz-toast'>
          <Text>{toast}</Text>
        </View>
      ) : null}
    </View>
  )
}
