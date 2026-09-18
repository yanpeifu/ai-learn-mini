import type {
  AnswerResult,
  AttemptDetail,
  AttemptHistory,
  AttemptStartResult,
  LevelsGenerateResult,
  OngoingAttempt,
  OutlineDetail,
  OutlineGenerateResult,
  OutlinePoint,
  Settlement,
  TemplateItem,
  UserPublic,
  UserStats
} from '@/types/api'

import { request } from './request'

/** 大纲生成 10–30 秒、出题 10–60 秒，所以这两个接口给更长的超时。 */
const OUTLINE_TIMEOUT = 40000
const LEVELS_TIMEOUT = 90000

export const api = {
  login(code: string) {
    return request<{ token: string; user: UserPublic }>({
      url: '/api/auth/login',
      method: 'POST',
      data: { code },
      auth: false
    })
  },

  templates() {
    return request<{ templates: TemplateItem[] }>({ url: '/api/templates', auth: false })
  },

  generateOutline(rawText: string) {
    return request<OutlineGenerateResult>({
      url: '/api/knowledge/outline',
      method: 'POST',
      data: { raw_text: rawText },
      timeout: OUTLINE_TIMEOUT
    })
  },

  saveOutline(outlineId: number, points: OutlinePoint[]) {
    return request<{ ok: boolean; points: OutlinePoint[] }>({
      url: `/api/knowledge/outline/${outlineId}`,
      method: 'PUT',
      data: { points }
    })
  },

  outlineDetail(outlineId: number) {
    return request<OutlineDetail>({ url: `/api/knowledge/outline/${outlineId}` })
  },

  generateLevels(outlineId: number) {
    return request<LevelsGenerateResult>({
      url: '/api/knowledge/levels',
      method: 'POST',
      data: { outline_id: outlineId },
      timeout: LEVELS_TIMEOUT
    })
  },

  startAttempt(outlineId: number) {
    return request<AttemptStartResult>({
      url: '/api/attempt/start',
      method: 'POST',
      data: { outline_id: outlineId }
    })
  },

  submitAnswer(attemptId: number, questionId: number, answer: string[], elapsedMs: number) {
    return request<AnswerResult>({
      url: `/api/attempt/${attemptId}/answer`,
      method: 'POST',
      data: { question_id: questionId, answer, elapsed_ms: elapsedMs }
    })
  },

  finishAttempt(attemptId: number) {
    return request<Settlement>({ url: `/api/attempt/${attemptId}/finish`, method: 'POST' })
  },

  attemptDetail(attemptId: number) {
    return request<AttemptDetail>({ url: `/api/attempt/${attemptId}` })
  },

  attempts(page = 1, size = 20) {
    return request<AttemptHistory>({ url: `/api/attempts?page=${page}&size=${size}` })
  },

  ongoingAttempt() {
    return request<{ attempt: OngoingAttempt | null }>({ url: '/api/attempt/ongoing' })
  },

  reportQuestion(questionId: number, reason: string, detail?: string) {
    return request<{ ok: boolean; disabled: boolean }>({
      url: `/api/questions/${questionId}/report`,
      method: 'POST',
      data: { reason, detail }
    })
  },

  userStats() {
    return request<UserStats>({ url: '/api/user/stats' })
  }
}
