import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api } from '@/services/api'
import { storage } from '@/services/storage'
import type { AnswerResult, PublicLevel, PublicQuestion, Settlement } from '@/types/api'

export interface QuizProgress {
  outlineId: number
  attemptId: number
  levels: PublicLevel[]
  levelIndex: number
  questionIndex: number
}

interface AttemptContextValue {
  progress: QuizProgress | null
  settlement: Settlement | null
  start: (outlineId: number) => Promise<QuizProgress>
  resume: (progress: QuizProgress) => void
  goTo: (levelIndex: number, questionIndex: number) => void
  submit: (question: PublicQuestion, answer: string[], elapsedMs: number) => Promise<AnswerResult>
  finish: () => Promise<Settlement>
  reset: () => void
}

const AttemptContext = createContext<AttemptContextValue | null>(null)

/** 当前闯关状态：进度同时写本地存储（切后台/退出不丢）。 */
export function AttemptProvider({ children }: { children: ReactNode }) {
  const [progress, setProgressState] = useState<QuizProgress | null>(null)
  const [settlement, setSettlement] = useState<Settlement | null>(null)

  const persist = useCallback((next: QuizProgress | null) => {
    setProgressState(next)
    if (next) storage.setProgress(next)
    else storage.clearProgress()
  }, [])

  const start = useCallback(
    async (outlineId: number) => {
      const result = await api.startAttempt(outlineId)
      const next: QuizProgress = {
        outlineId,
        attemptId: result.attempt_id,
        levels: result.levels,
        levelIndex: 0,
        questionIndex: 0
      }
      persist(next)
      setSettlement(null)
      return next
    },
    [persist]
  )

  const resume = useCallback(
    (next: QuizProgress) => {
      persist(next)
    },
    [persist]
  )

  const goTo = useCallback(
    (levelIndex: number, questionIndex: number) => {
      setProgressState((current) => {
        if (!current) return current
        const next = { ...current, levelIndex, questionIndex }
        storage.setProgress(next)
        return next
      })
    },
    []
  )

  const submit = useCallback(
    async (question: PublicQuestion, answer: string[], elapsedMs: number) => {
      if (!progress) throw new Error('还没有开始闯关')
      return api.submitAnswer(progress.attemptId, question.id, answer, elapsedMs)
    },
    [progress]
  )

  const finish = useCallback(async () => {
    if (!progress) throw new Error('还没有开始闯关')
    const result = await api.finishAttempt(progress.attemptId)
    setSettlement(result)
    storage.clearProgress()
    setProgressState(null)
    return result
  }, [progress])

  const reset = useCallback(() => {
    persist(null)
    setSettlement(null)
  }, [persist])

  const value = useMemo(
    () => ({ progress, settlement, start, resume, goTo, submit, finish, reset }),
    [progress, settlement, start, resume, goTo, submit, finish, reset]
  )

  return <AttemptContext.Provider value={value}>{children}</AttemptContext.Provider>
}

export function useAttempt(): AttemptContextValue {
  const value = useContext(AttemptContext)
  if (!value) throw new Error('useAttempt 必须在 AttemptProvider 内使用')
  return value
}
